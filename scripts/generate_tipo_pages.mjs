import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

// ── slug ─────────────────────────────────────────────────────────────────────

function toSlug(str) {
  return str
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

// ── phone ─────────────────────────────────────────────────────────────────────

function formatPhone(p) {
  if (!p || p === 'NULL') return null;
  const s = p.trim();
  if (!s) return null;
  if (s.startsWith('(47)') || s.startsWith('+55 47') || s.startsWith('47 ')) return s;
  return `(47) ${s}`;
}

// ── SQL value parser ──────────────────────────────────────────────────────────
// Splits a VALUES row like (1,'foo','it''s',NULL,2) into an array of raw values.
// Handles: single-quoted strings (with '' escaping), NULL, numbers.

function parseRow(rowStr) {
  const s = rowStr.trim().replace(/^\(/, '').replace(/\)$/, '');
  const values = [];
  let i = 0;
  while (i < s.length) {
    if (s[i] === ' ' || s[i] === '\t') { i++; continue; }
    if (s[i] === ',') { i++; continue; }
    if (s[i] === "'") {
      // quoted string
      let str = '';
      i++; // skip opening quote
      while (i < s.length) {
        if (s[i] === "'" && s[i + 1] === "'") {
          str += "'";
          i += 2;
        } else if (s[i] === "'") {
          i++; // skip closing quote
          break;
        } else {
          str += s[i++];
        }
      }
      values.push(str);
    } else {
      // unquoted (NULL or number)
      let tok = '';
      while (i < s.length && s[i] !== ',' && s[i] !== ' ') tok += s[i++];
      values.push(tok === 'NULL' ? null : tok);
    }
  }
  return values;
}

// ── INSERT block parser ───────────────────────────────────────────────────────
// Finds all INSERT INTO `tableName` blocks and returns rows as arrays.

function parseInserts(sql, tableName) {
  const rows = [];
  const blockRe = new RegExp(
    `INSERT INTO \`${tableName}\`[^;]+?VALUES\\s*([\\s\\S]*?);`,
    'gi'
  );
  let blockMatch;
  while ((blockMatch = blockRe.exec(sql)) !== null) {
    const valueSection = blockMatch[1];
    // Walk char-by-char to split tuples respecting quoted commas
    let depth = 0;
    let start = -1;
    for (let i = 0; i < valueSection.length; i++) {
      const ch = valueSection[i];
      if (ch === '(') {
        if (depth === 0) start = i;
        depth++;
      } else if (ch === ')') {
        depth--;
        if (depth === 0 && start !== -1) {
          const rowStr = valueSection.slice(start, i + 1);
          rows.push(parseRow(rowStr));
          start = -1;
        }
      } else if (ch === "'" && depth > 0) {
        // skip over quoted string
        i++;
        while (i < valueSection.length) {
          if (valueSection[i] === "'" && valueSection[i + 1] === "'") {
            i += 2;
          } else if (valueSection[i] === "'") {
            break;
          } else {
            i++;
          }
        }
      }
    }
  }
  return rows;
}

// ── HTML content builder ──────────────────────────────────────────────────────

function esc(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function generateContent(tipoName, anunciantes, cidadeMap) {
  const count = anunciantes.length;
  const heading = `
<h2 style="color:#CC0000; font-family:Arial,sans-serif; font-size:16px; margin:0 0 10px 0; padding-bottom:6px; border-bottom:2px solid #CC0000;">
  ${esc(tipoName)}
  <small style="font-size:12px; color:#888; font-weight:normal;">(${count} encontrado${count !== 1 ? 's' : ''})</small>
</h2>`;

  if (count === 0) {
    return `${heading}
<p style="font-family:Arial,sans-serif; font-size:13px; color:#888; margin:10px 0;">
  Nenhum anunciante cadastrado para esta categoria.
</p>`;
  }

  const items = anunciantes.map((row) => {
    // anunciantes columns: id, nome, observacao, endereco, telefone1, telefone2, telefone3, site, tipo, cidade
    const [, nome, observacao, endereco, tel1, tel2, tel3, site, , cidadeId] = row;
    const cidadeNome = cidadeMap[cidadeId] || '';

    const phones = [tel1, tel2, tel3]
      .map(formatPhone)
      .filter(Boolean)
      .map(p => `📞 ${esc(p)}`)
      .join('<br>\n    ');

    const siteLink = site
      ? `🌐 <a href="http://${esc(site)}" style="color:#336699;" target="_blank">${esc(site)}</a>`
      : '';

    return `
  <div style="border-bottom:1px solid #e0e0e0; padding:8px 0; margin-bottom:4px;">
    <strong style="font-family:Arial,sans-serif; font-size:13px; color:#333;">📋 ${esc(nome)}</strong><br>
    ${endereco ? `📍 ${esc(endereco)}<br>\n    ` : ''}${phones ? `${phones}<br>\n    ` : ''}${cidadeNome ? `🏙️ ${esc(cidadeNome)}<br>\n    ` : ''}${siteLink ? `${siteLink}<br>\n    ` : ''}${observacao ? `<em style="font-size:12px; color:#666;">${esc(observacao)}</em>` : ''}
  </div>`;
  }).join('\n');

  return `${heading}
<div style="font-family:Arial,sans-serif; font-size:13px; color:#333;">
  ${items}
</div>`;
}

// ── main ──────────────────────────────────────────────────────────────────────

const sqlPath = join(ROOT, 'db', 'aquitemjoinville.sql');
const templatePath = join(ROOT, 'rip', 'aquitemjoinville', 'template.html');
const outDir = join(ROOT, 'rip', 'aquitemjoinville');

console.log('Reading SQL dump…');
const sql = readFileSync(sqlPath, 'utf8');

console.log('Parsing tables…');
const tipoRows = parseInserts(sql, 'tipoanunciante');
const anuncianteRows = parseInserts(sql, 'anunciantes');
const cidadeRows = parseInserts(sql, 'cidade');

console.log(`  tipoanunciante: ${tipoRows.length} rows`);
console.log(`  anunciantes:    ${anuncianteRows.length} rows`);
console.log(`  cidade:         ${cidadeRows.length} rows`);

// cidade: id → name
const cidadeMap = {};
for (const [id, nome] of cidadeRows) cidadeMap[id] = nome;

// anunciantes grouped by tipo (idTipo)
const byTipo = {};
for (const row of anuncianteRows) {
  const tipoId = row[8]; // column index 8 = tipo
  if (!byTipo[tipoId]) byTipo[tipoId] = [];
  byTipo[tipoId].push(row);
}

console.log('Reading template…');
const template = readFileSync(templatePath, 'utf8');

if (!template.includes('<!-- CONTENT HERE -->')) {
  console.error('ERROR: placeholder <!-- CONTENT HERE --> not found in template!');
  process.exit(1);
}

mkdirSync(outDir, { recursive: true });

let written = 0;
let skipped = 0;

console.log('Generating pages…');
for (const [idTipo, tipoName] of tipoRows) {
  const slug = toSlug(tipoName);
  if (!slug) { skipped++; continue; }

  const anunciantes = byTipo[idTipo] || [];
  const content = generateContent(tipoName, anunciantes, cidadeMap);
  const html = template
    .replace('<title>Aquitemjoinville.com.br - PRINCIPAL</title>', `<title>Aqui Tem Joinville - ${tipoName}</title>`)
    .replace('         <!-- CONTENT HERE -->', content);

  const outPath = join(outDir, `${slug}.html`);
  writeFileSync(outPath, html, 'utf8');
  console.log(`  ✓ ${slug}.html (${anunciantes.length} anunciante${anunciantes.length !== 1 ? 's' : ''})`);
  written++;
}

console.log(`\nDone. ${written} pages written, ${skipped} skipped.`);
