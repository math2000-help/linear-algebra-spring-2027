// check_math.mjs -- render every equation in the BUILT site with KaTeX and the site's macros.
// An undefined macro, unbalanced brace or unsupported environment throws; this fails the build.
//
//   node tools/check_math.mjs build/site site/macros.json
// Needs `katex` (npm install katex) resolvable from KATEX_FROM (a directory containing node_modules).
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(process.env.KATEX_FROM ? path.join(process.env.KATEX_FROM, 'x.js') : import.meta.url);
const katex = require('katex');

const [siteDir, macrosFile] = process.argv.slice(2);
const raw = JSON.parse(fs.readFileSync(macrosFile, 'utf8'));
const macros = Object.fromEntries(Object.entries(raw).map(([k, v]) => ['\\' + k, v]));

function* walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (e.name === 'index.html') yield p;
  }
}
const unescape = s => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');

let total = 0, bad = 0;
for (const file of walk(siteDir)) {
  const html = fs.readFileSync(file, 'utf8');
  const re = /<(span|div) class="arithmatex">([\s\S]*?)<\/\1>/g;
  let m;
  while ((m = re.exec(html))) {
    let body = unescape(m[2]).trim();
    const display = body.startsWith('\\[');
    body = body.replace(/^\\\(|\\\)$/g, '').replace(/^\\\[|\\\]$/g, '');
    total++;
    try {
      katex.renderToString(body, { displayMode: display, macros: { ...macros }, throwOnError: true, strict: 'error' });
    } catch (err) {
      bad++;
      console.log(`MATH ERROR in ${path.relative(siteDir, file)}: ${err.message}\n   ${body.slice(0, 160).replace(/\s+/g, ' ')}`);
    }
  }
}
console.log(`${total} math expressions checked, ${bad} errors`);
process.exit(bad ? 1 : 0);
