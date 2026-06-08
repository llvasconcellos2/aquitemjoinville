#!/usr/bin/env python3
"""
Fix absolute localhost URLs in the rip/aquitemjoinville/ static archive and
generate missing weblink view pages from db/aquitemjoinville.sql.

Usage:
    python scripts/fix_links.py
"""

import os
import re
import html as html_mod

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RIP_SUBDIR   = os.path.join(PROJECT_ROOT, "rip", "aquitemjoinville")
RIP_ROOT_FILES = [
    os.path.join(PROJECT_ROOT, "rip", "aquitemjoinville.html"),
    os.path.join(PROJECT_ROOT, "rip", "index.html"),
]
SQL_FILE      = os.path.join(PROJECT_ROOT, "db", "aquitemjoinville.sql")
TEMPLATE_FILE = os.path.join(RIP_SUBDIR, "index.php@option=com_weblinks&catid=31&Itemid=5.html")

LOCALHOST_PREFIXES = [
    "http://localhost:8080/aquitemjoinville/",
    "http://localhost/aquitemjoinville/",
]

# ── URL conversion ─────────────────────────────────────────────────────────────
def path_to_wget(path):
    """Strip localhost prefix result -> wget filename format."""
    if "?" in path:
        base, query = path.split("?", 1)
        query = query.replace("&amp;", "&")
        return f"{base}@{query}.html"
    return path


_PREFIX_ALT = "(?:" + "|".join(re.escape(p) for p in LOCALHOST_PREFIXES) + ")"

# Matches localhost URLs in href/src attributes
_ATTR_PATTERN = re.compile(
    r'(href|src)="' + _PREFIX_ALT + r'([^"]*)"',
    re.IGNORECASE,
)

# Matches localhost URLs in JS string assignments:  = "http://localhost/..."
_JS_PATTERN = re.compile(
    r'(=\s*)"' + _PREFIX_ALT + r'([^"]*)"',
    re.IGNORECASE,
)

# Matches localhost URLs in single-quoted JS strings, e.g. window.open('http://localhost/...')
_SINGLE_QUOTE_PATTERN = re.compile(
    r"'(?:" + _PREFIX_ALT + r")([^']*)'",
    re.IGNORECASE,
)

# Matches relative index(2).php?query hrefs that were never wget-converted
_REL_PHP_PATTERN = re.compile(
    r'(href|src)="(index2?\.php)\?([^"#]*)"',
    re.IGNORECASE,
)


def fix_content(content, prefix_dir=""):
    """Replace every absolute localhost URL and un-converted relative PHP URL.

    prefix_dir is prepended to converted absolute paths (used for files one
    level above rip/aquitemjoinville/ that need an 'aquitemjoinville/' prefix).
    """
    count = [0]

    def replace_attr(m):
        attr = m.group(1)
        path = prefix_dir + path_to_wget(m.group(2))
        count[0] += 1
        return f'{attr}="{path}"'

    def replace_js(m):
        eq = m.group(1)
        path = prefix_dir + path_to_wget(m.group(2))
        count[0] += 1
        return f'{eq}"{path}"'

    def replace_single_quote(m):
        path = prefix_dir + path_to_wget(m.group(1).replace("&amp;", "&"))
        count[0] += 1
        return f"'{path}'"

    def replace_rel_php(m):
        attr = m.group(1)
        base = m.group(2)
        query = m.group(3).replace("&amp;", "&")
        count[0] += 1
        return f'{attr}="{base}@{query}.html"'

    content = _ATTR_PATTERN.sub(replace_attr, content)
    content = _JS_PATTERN.sub(replace_js, content)
    content = _SINGLE_QUOTE_PATTERN.sub(replace_single_quote, content)
    content = _REL_PHP_PATTERN.sub(replace_rel_php, content)
    return content, count[0]


# ── SQL parsing ────────────────────────────────────────────────────────────────
def _unescape_sql(s):
    return s.replace("\\'", "'").replace("\\\\", "\\").replace("\\r\\n", "\n").replace("\\n", "\n")


def parse_sql(sql_file):
    """Return (weblinks_dict, categories_dict) parsed from the SQL dump."""
    with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
        sql = f.read()

    weblinks = {}
    categories = {}

    # jos_weblinks ─ columns: id, catid, sid, title, url, description, ...
    wl_block = re.search(r"INSERT INTO `jos_weblinks`[^;]+;", sql, re.DOTALL)
    if wl_block:
        row_re = re.compile(
            r"\((\d+),\s*(\d+),\s*\d+,"           # id, catid, sid
            r"\s*'((?:[^'\\]|\\.)*)',"             # title
            r"\s*'((?:[^'\\]|\\.)*)',"             # url
            r"\s*'((?:[^'\\]|\\.)*)',"             # description
        )
        for m in row_re.finditer(wl_block.group(0)):
            wid = int(m.group(1))
            weblinks[wid] = {
                "catid":       int(m.group(2)),
                "title":       _unescape_sql(m.group(3)),
                "url":         _unescape_sql(m.group(4)),
                "description": _unescape_sql(m.group(5)),
            }

    # jos_categories filtered to section = 'com_weblinks'
    # columns: id, parent_id, title, name, image, section, ...
    cat_block = re.search(r"INSERT INTO `jos_categories`[^;]+;", sql, re.DOTALL)
    if cat_block:
        cat_re = re.compile(
            r"\((\d+),\s*\d+,"                    # id, parent_id
            r"\s*'((?:[^'\\]|\\.)*)',"             # title
            r"\s*'(?:[^'\\]|\\.)*',"              # name
            r"\s*'[^']*',"                         # image
            r"\s*'com_weblinks',"                  # section = com_weblinks
        )
        for m in cat_re.finditer(cat_block.group(0)):
            cid = int(m.group(1))
            categories[cid] = _unescape_sql(m.group(2))

    return weblinks, categories


# ── Missing-page generation ────────────────────────────────────────────────────
_CONTENT_REGION = re.compile(
    r'<div class="componentheading">.*?</div>.*?<div class="back_button">.*?</div>',
    re.DOTALL,
)


def generate_weblink_page(weblink, template_content):
    """Stamp a weblink's data into the Joomla template, return the new HTML."""
    title   = html_mod.escape(weblink["title"])
    url_esc = html_mod.escape(weblink["url"])
    desc    = weblink["description"].strip()
    desc_html = f"\n\t\t\t\t\t\t\t\t<p>{html_mod.escape(desc)}</p>" if desc else ""

    new_region = (
        f'\t\t\t\t\t\t\t<div class="componentheading">{title}</div>\n'
        f'\t\t\t\t\t\t\t<div style="padding:10px;">'
        f'{desc_html}\n'
        f'\t\t\t\t\t\t\t\t<p>'
        f'<a href="{url_esc}" target="_blank" class="category">Acessar: {title}</a>'
        f'</p>\n'
        f'\t\t\t\t\t\t\t\t<iframe src="{url_esc}" width="100%" height="400" frameborder="0">'
        f'<a href="{url_esc}" target="_blank">{url_esc}</a></iframe>\n'
        f'\t\t\t\t\t\t\t</div>\n'
        f'\t\t\t\t\t\t\t<div class="back_button">'
        f"<a href='javascript:history.go(-1)'>[ Voltar ]</a>"
        f'</div>'
    )

    page = _CONTENT_REGION.sub(new_region, template_content, count=1)
    page = re.sub(
        r"<title>[^<]*</title>",
        f"<title>Aquitemjoinville.com.br - {title}</title>",
        page,
        count=1,
    )
    return page


# ── File helpers ───────────────────────────────────────────────────────────────
def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── Phase 1 — fix absolute URLs ────────────────────────────────────────────────
def phase_fix():
    total_files = 0
    total_replacements = 0

    # Files inside rip/aquitemjoinville/
    for fname in sorted(os.listdir(RIP_SUBDIR)):
        fpath = os.path.join(RIP_SUBDIR, fname)
        if not (os.path.isfile(fpath) and fname.lower().endswith(".html")):
            continue
        content = read_file(fpath)
        new_content, count = fix_content(content, prefix_dir="")
        if count:
            write_file(fpath, new_content)
            total_files += 1
            total_replacements += count

    # Root-level rip/ files (one directory up -> prepend aquitemjoinville/)
    for fpath in RIP_ROOT_FILES:
        if not os.path.isfile(fpath):
            continue
        content = read_file(fpath)
        new_content, count = fix_content(content, prefix_dir="aquitemjoinville/")
        if count:
            write_file(fpath, new_content)
            total_files += 1
            total_replacements += count

    print(f"Phase 1 — fixed {total_replacements} URLs across {total_files} files")
    return total_replacements


# ── Phase 2 — detect and generate missing weblink pages ───────────────────────

# Matches converted weblink view filenames: index.php@option=com_weblinks&task=view&catid=X&id=Y.html
_WEBLINK_VIEW = re.compile(
    r"index\.php@option=com_weblinks&task=view&catid=(\d+)&id=(\d+)\.html"
)


def collect_missing_hrefs():
    """Scan all HTML files and return hrefs whose targets don't exist on disk."""
    missing = set()
    href_re = re.compile(r'href="([^"#][^"]*\.html)"')

    for fname in os.listdir(RIP_SUBDIR):
        fpath = os.path.join(RIP_SUBDIR, fname)
        if not (os.path.isfile(fpath) and fname.lower().endswith(".html")):
            continue
        content = read_file(fpath)
        for m in href_re.finditer(content):
            href = m.group(1)
            if href.startswith(("http://", "https://", "//")):
                continue
            target = os.path.join(RIP_SUBDIR, href)
            if not os.path.isfile(target):
                missing.add(href)

    return sorted(missing)


def _is_generated_page(filepath):
    """Return True if this file was previously generated by this script
    (identified by containing the aquitemjoinville site title)."""
    try:
        content = read_file(filepath)
        return "Aquitemjoinville.com.br -" in content
    except OSError:
        return False


def phase_generate():
    missing = collect_missing_hrefs()

    # Also include previously generated pages that need to be regenerated
    # (identified by the aquitemjoinville title prefix we inject).
    for fname in os.listdir(RIP_SUBDIR):
        fpath = os.path.join(RIP_SUBDIR, fname)
        if _WEBLINK_VIEW.match(fname) and _is_generated_page(fpath):
            if fname not in missing:
                missing.append(fname)

    missing = sorted(set(missing))

    if not missing:
        print("Phase 2 — no missing local hrefs found")
        return

    print(f"Phase 2 — {len(missing)} weblink pages to generate/regenerate")

    weblinks, categories = parse_sql(SQL_FILE)
    template = read_file(TEMPLATE_FILE)

    generated = 0
    skipped = []

    for href in missing:
        m = _WEBLINK_VIEW.match(href)
        if not m:
            skipped.append(href)
            continue

        wl_id = int(m.group(2))
        if wl_id not in weblinks:
            print(f"  WARN  weblink id={wl_id} not found in database ({href})")
            skipped.append(href)
            continue

        page = generate_weblink_page(weblinks[wl_id], template)
        out_path = os.path.join(RIP_SUBDIR, href)
        write_file(out_path, page)
        generated += 1
        print(f"  GEN   {href}  ->  {weblinks[wl_id]['title']}")

    print(f"\n  Generated {generated} weblink pages")
    if skipped:
        print(f"  Skipped {len(skipped)} non-weblink missing hrefs:")
        for s in skipped:
            print(f"    {s}")


# ── Verification helper ────────────────────────────────────────────────────────
def phase_verify():
    remaining = []
    for fname in os.listdir(RIP_SUBDIR):
        fpath = os.path.join(RIP_SUBDIR, fname)
        if not (os.path.isfile(fpath) and fname.lower().endswith(".html")):
            continue
        if "localhost" in read_file(fpath).lower():
            remaining.append(fname)

    for fpath in RIP_ROOT_FILES:
        if os.path.isfile(fpath) and "localhost" in read_file(fpath).lower():
            remaining.append(os.path.basename(fpath))

    if remaining:
        print(f"\nVerify — {len(remaining)} files still contain 'localhost':")
        for f in remaining:
            print(f"  {f}")
    else:
        print("\nVerify — no remaining 'localhost' references found")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    phase_fix()
    phase_generate()
    phase_verify()
