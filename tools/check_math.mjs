// check_math.mjs -- parse every equation in the BUILT site with MathJax and the site's macros.
// An undefined macro, unbalanced brace or bad environment makes MathJax emit an <merror>; this fails the build.
//
//   node tools/check_math.mjs build/site site/macros.json
// Needs `mathjax-full` (npm install mathjax-full) resolvable from NODE_PATH or the working directory.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(process.env.MATHJAX_FROM ? path.join(process.env.MATHJAX_FROM, 'x.js') : import.meta.url);
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { SerializedMmlVisitor } = require('mathjax-full/js/core/MmlTree/SerializedMmlVisitor.js');
const { STATE } = require('mathjax-full/js/core/MathItem.js');
require('mathjax-full/js/input/tex/base/BaseConfiguration.js');
require('mathjax-full/js/input/tex/ams/AmsConfiguration.js');
require('mathjax-full/js/input/tex/newcommand/NewcommandConfiguration.js');
require('mathjax-full/js/input/tex/configmacros/ConfigMacrosConfiguration.js');

const [siteDir, macrosFile] = process.argv.slice(2);
const macros = JSON.parse(fs.readFileSync(macrosFile, 'utf8'));
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
// same packages the site loads (tex-mml-chtml) minus `noundefined`, so unknown macros are errors, not red text
const tex = new TeX({ packages: ['base', 'ams', 'newcommand', 'configmacros'], macros, processEscapes: true });
const doc = mathjax.document('', { InputJax: tex });
const visitor = new SerializedMmlVisitor();

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
    let out;
    try { out = visitor.visitTree(doc.convert(body, { display, end: STATE.CONVERT })); }
    catch (err) { out = '<merror>' + err.message; }
    if (out.includes('merror')) {
      bad++;
      const msg = (out.match(/<merror[^>]*data-mjx-error="([^"]*)"/) || out.match(/<merror[\s\S]*?>([\s\S]*?)<\/merror>/) || [])[1] || out.slice(0, 120);
      console.log(`MATH ERROR in ${path.relative(siteDir, file)}: ${msg}\n   ${body.slice(0, 160).replace(/\s+/g, ' ')}`);
    }
  }
}
console.log(`${total} math expressions checked, ${bad} errors`);
process.exit(bad ? 1 : 0);
