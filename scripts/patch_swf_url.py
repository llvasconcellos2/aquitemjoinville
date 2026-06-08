"""
Patches aquitemjoinville_flex.swf to replace the old PHP URL with a local XML path.

Steps:
  1. Decompress the zlib body (CWS format)
  2. Replace old string + u30 length prefix with new string + u30 prefix
  3. Find the DoABC SWF tag containing the string and correct its body-length field
  4. Update the SWF FileLength header
  5. Recompress and save
"""
import zlib, struct, os

SWF_PATH = os.path.join(os.path.dirname(__file__), "..", "flex", "module_src", "aquitemjoinville_flex.swf")
OLD_STR = b"http://www.aquitemjoinville.com.br/modulo_segmentos_flex/Tipoanunciante.php"
NEW_STR = b"modulo_segmentos_flex/tipoanunciante.xml"
DOABC_TAG_CODE = 82

data = open(SWF_PATH, "rb").read()
assert data[:3] == b"CWS", "Expected zlib-compressed SWF (CWS)"
header = data[:8]
body = zlib.decompress(data[8:])

# --- locate old string ---
str_idx = body.find(OLD_STR)
assert str_idx != -1, "Old string not found in decompressed body"
assert body[str_idx - 1] == len(OLD_STR), f"Unexpected u30 prefix byte: 0x{body[str_idx-1]:02X}"
print(f"Found old string at decompressed offset {str_idx}, u30 prefix=0x{body[str_idx-1]:02X}")

# --- walk SWF tags to find the DoABC tag that contains the string ---
nbits = (body[0] >> 3) & 0x1F
rect_bytes = (5 + 4 * nbits + 7) // 8
pos = rect_bytes + 4  # skip RECT + FrameRate (2B) + FrameCount (2B)

doabc_length_offset = None
doabc_old_length = None

while pos < len(body):
    tag_start = pos
    code_and_length = struct.unpack_from("<H", body, pos)[0]
    code = code_and_length >> 6
    raw_len = code_and_length & 0x3F

    if raw_len == 63:
        tag_length = struct.unpack_from("<i", body, pos + 2)[0]
        header_size = 6
    else:
        tag_length = raw_len
        header_size = 2

    tag_body_start = tag_start + header_size
    tag_body_end = tag_body_start + tag_length

    if tag_body_start <= str_idx < tag_body_end:
        assert code == DOABC_TAG_CODE, f"String is inside tag {code}, expected DoABC ({DOABC_TAG_CODE})"
        doabc_length_offset = tag_start + 2  # the s32 length field is 2 bytes into the tag header
        doabc_old_length = tag_length
        print(f"DoABC tag found at body offset {tag_start}, length={tag_length}")
        break

    pos = tag_body_end
    if code == 0:
        break

assert doabc_length_offset is not None, "DoABC tag not found"

# --- replace string (u30 prefix + bytes) ---
size_diff = len(OLD_STR) - len(NEW_STR)  # bytes removed
new_encoded = bytes([len(NEW_STR)]) + NEW_STR
new_body = body[: str_idx - 1] + new_encoded + body[str_idx + len(OLD_STR) :]
assert len(new_body) == len(body) - size_diff

# --- fix DoABC tag body-length field ---
new_doabc_length = doabc_old_length - size_diff
body_arr = bytearray(new_body)
struct.pack_into("<i", body_arr, doabc_length_offset, new_doabc_length)
new_body = bytes(body_arr)
print(f"DoABC length: {doabc_old_length} -> {new_doabc_length} (fixed)")

# --- update SWF FileLength (uncompressed size) ---
new_file_length = 8 + len(new_body)
new_header = header[:4] + struct.pack("<I", new_file_length)

with open(SWF_PATH, "wb") as f:
    f.write(new_header + zlib.compress(new_body, 9))

print(f"Saved. Body: {len(body)} -> {len(new_body)} bytes. Done.")
