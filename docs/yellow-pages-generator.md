# Plan: Generate `/rip/aquitemjoinville/{tipo}.html` pages

## Context

The project is a static HTML archive of aquitemjoinville.com.br — a Joinville yellow-pages directory. The SQL dump at `db/aquitemjoinville.sql` contains all the data. The goal is to generate one HTML page per business category (`tipoanunciante`), each listing all matching businesses (`anunciantes`) with full contact info.

**Why a script, not direct generation:** There are 1000+ tipos and 10,000+ anunciantes. Generating all HTML directly through Claude would exceed the 32,000 output-token limit. The solution is to write a single Node.js generator script (~200 lines) that Claude emits once, and then run it locally to produce all files.

---

## Approach: Single Node.js generator script

**File to create:** `scripts/generate_tipo_pages.mjs`

The script:

1. Reads and parses `db/aquitemjoinville.sql` (15,965 lines, phpMyAdmin multi-row INSERT format)
2. Builds in-memory maps for `tipoanunciante`, `anunciantes`, and `cidade`
3. Reads `rip/aquitemjoinville/template.html` once
4. For each tipo → slugifies the name → finds matching anunciantes → injects HTML content → writes `rip/aquitemjoinville/{slug}.html`

---

## SQL parsing notes

- File uses multi-row INSERT: `INSERT INTO \`table\` (\`col\`, ...) VALUES\n(row),(row),...;`
- `anunciantes` spans **25 separate INSERT batches** (each ~440 rows)
- String escaping: `''` (double single-quote), not `\'`
- NULL values are literal unquoted `NULL`
- Column order for `anunciantes`: `id, nome, observacao, endereco, telefone1, telefone2, telefone3, site, tipo, cidade`

Parser strategy: regex to locate each INSERT block per table, then a character-level state machine to split comma-separated tuples (handles quoted strings, NULLs, and nested commas inside string values).

---

## Key functions in the script

```js
toSlug(str); // NFD normalize → strip diacritics → lowercase → [^a-z0-9]+ → "_"
formatPhone(p); // if already starts with "(47)" leave as-is; else prepend "(47) "
parseInserts(sql, tableName); // returns array of row-arrays for given table
generateContent(tipoName, rows, cidadeMap); // returns HTML string for the CONTENT placeholder
```

---

## Content HTML structure (injected at `<!-- CONTENT HERE -->`)

Yellow-pages style, inline styles to match the template's aesthetic (Arial, #CC0000 heading):

```html
<h2 style="color:#CC0000; font-family:Arial; font-size:16px; margin:0 0 10px;">
  Dentistas <small style="font-size:12px; color:#666;">(3 encontrados)</small>
</h2>
<div style="font-family:Arial; font-size:13px; color:#333;">
  <div style="border-bottom:1px solid #ddd; padding:8px 0;">
    <strong>📋 Nome da Empresa</strong><br />
    📍 Endereço<br />
    📞 (47) 3436-0878<br />
    🏙️ Joinville
  </div>
  <!-- repeat per anunciante -->
</div>
```

Fields shown (with emojis):

- `nome` — 📋 bold
- `endereco` — 📍
- `telefone1/2/3` — 📞 (each non-null phone on its own line, "(47) " prepended if missing)
- `cidade` — 🏙️ (resolved via cidade map)
- `site` — 🌐 (only if non-null)
- `observacao` — shown as small italic note if non-null

Types with zero anunciantes still get a page with "Nenhum anunciante cadastrado."

---

## Critical files

| File                                 | Role                         |
| ------------------------------------ | ---------------------------- |
| `db/aquitemjoinville.sql`            | Data source (read-only)      |
| `rip/aquitemjoinville/template.html` | Layout template (read-only)  |
| `scripts/generate_tipo_pages.mjs`    | **Script to create**         |
| `rip/aquitemjoinville/{slug}.html`   | **~1000+ files to generate** |

---

## Execution

```bash
node scripts/generate_tipo_pages.mjs
```

Expected output: one line per file written, e.g. `✓ dentistas.html (3 anunciantes)`, plus a final summary count.

---

## Verification

1. Run the script — check console output for errors and file count
2. Open `rip/aquitemjoinville/dentistas.html` in a browser — should show the full template layout with Dentistas listings in the center column
3. Spot-check a few slugs: `abrasivos.html`, `academias_desportivas.html`
4. Verify phone formatting: a raw `3436-0878` should appear as `(47) 3436-0878`
5. Verify no double-prefix: any phone already starting with `(47)` should be unchanged
