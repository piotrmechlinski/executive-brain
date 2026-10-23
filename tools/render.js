// Drawing for build_doc.py, with Playwright's Chromium.
//
//   node tools/render.js mermaid <diagrams.json> <outdir>   each diagram as an SVG (for the PDF) and a PNG (for Word)
//   node tools/render.js pdf <page.html> <out.pdf>            an HTML page printed to an A4 PDF
//
// diagrams.json is {"theme": {...}, "items": [{"id": "fig1", "code": "flowchart LR ..."}]}.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const tools = __dirname;
const fonts = 'file://' + path.join(tools, 'fonts');

async function mermaid(input, outdir) {
  const { theme: t, items } = JSON.parse(fs.readFileSync(input, 'utf8'));
  const page = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: Archivo; src: url('${fonts}/Archivo-Regular.ttf'); font-weight: 400; }
@font-face { font-family: Archivo; src: url('${fonts}/Archivo-Bold.ttf'); font-weight: 700; }
body { margin: 0; background: #FFFFFF; font-family: Archivo; }
#out { display: inline-block; padding: 6px; background: #FFFFFF; }
</style><script>${fs.readFileSync(path.join(tools, 'vendor', 'mermaid.min.js'), 'utf8')}</script></head>
<body><div id="out"></div></body></html>`;
  fs.mkdirSync(outdir, { recursive: true });
  const html = path.join(outdir, 'render.html');
  fs.writeFileSync(html, page);
  const browser = await chromium.launch();
  const tab = await browser.newPage({ deviceScaleFactor: 3 });
  await tab.goto('file://' + html);
  await tab.evaluate(async (t) => {
    await document.fonts.load('13px Archivo');
    await document.fonts.load('bold 13px Archivo');
    mermaid.initialize({
      startOnLoad: false, securityLevel: 'strict', theme: 'base', fontFamily: 'Archivo',
      flowchart: { htmlLabels: true, curve: 'basis', padding: 10, useMaxWidth: false },
      themeVariables: {
        fontFamily: 'Archivo', fontSize: '13px', background: '#FFFFFF', primaryColor: '#FFFFFF',
        primaryBorderColor: t.ink, primaryTextColor: t.ink, secondaryColor: t.soft, tertiaryColor: t.soft,
        lineColor: t.muted, clusterBkg: t.soft, clusterBorder: t.rule, edgeLabelBackground: '#FFFFFF', titleColor: t.accent,
        taskBkgColor: t.accent, critBkgColor: t.alert || '#CF222E', doneTaskBkgColor: t.muted,
      },
    });
  }, t);
  for (const { id, code } of items) {
    const svg = await tab.evaluate(async ([id, code]) => {
      const { svg } = await mermaid.render('m_' + id, code);
      document.getElementById('out').innerHTML = svg;
      return svg;
    }, [id, code]);
    fs.writeFileSync(path.join(outdir, id + '.svg'), svg);
    await (await tab.$('#out')).screenshot({ path: path.join(outdir, id + '.png') });
  }
  await browser.close();
  fs.unlinkSync(html);
}

async function pdf(html, out) {
  const browser = await chromium.launch();
  const tab = await browser.newPage({ viewport: { width: 1160, height: 900 } });
  await tab.goto('file://' + path.resolve(html));
  // Every font the page declares, including one used only in the page footer, which Chrome would not load by itself.
  await tab.evaluate(() => Promise.all([...document.fonts].map((f) => f.load())).then(() => document.fonts.ready));
  // A page with Mermaid diagrams, such as the project map, says when they are drawn.
  await tab.waitForFunction(() => !document.querySelector('pre.mermaid') || window.__ready === true, null, { timeout: 60000 });
  await tab.pdf({ path: out, format: 'A4', printBackground: true, preferCSSPageSize: true });
  await browser.close();
}

const [, , mode, a, b] = process.argv;
(mode === 'mermaid' ? mermaid(a, b) : pdf(a, b)).catch((e) => { console.error(e.message || e); process.exit(1); });
