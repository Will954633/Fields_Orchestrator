#!/usr/bin/env node
/**
 * fit_check.js — Browser-based section overflow detector for V4 appraisals.
 *
 * Loads a generated V4 appraisal HTML file in headless Chrome at A4 dimensions,
 * measures every <div class="page" data-section="..."> for content overflow,
 * and writes a JSON report of per-section measurements.
 *
 * Phase 1 of Layer 2: observational only. The generator records measurements
 * to the audit but does not yet re-render overflowing sections with compact
 * variants. That re-render loop is Phase 2.
 *
 * Usage:
 *   node fit_check.js <html_path> <output_json_path>
 *
 * Output JSON shape:
 *   {
 *     "html_path": "...",
 *     "viewport": {"width": 794, "height": 1123},
 *     "sections": [
 *       {
 *         "section_key": "01_right",
 *         "page_index": 4,
 *         "client_height_px": 1123,
 *         "scroll_height_px": 1145,
 *         "overflow_px": 22,
 *         "overflow": true
 *       },
 *       ...
 *     ],
 *     "summary": { "sections_measured": 10, "overflows": 1 }
 *   }
 */

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

// A4 at 96 DPI = 210mm × 297mm → 794 × 1123 px.
// `.page` in preview.html has `width: 210mm; height: 297mm; overflow: hidden`
// so the rendered .page element should be exactly 1123px tall when laid out.
const VIEWPORT = { width: 794, height: 1123, deviceScaleFactor: 1 };

function findChromePath() {
  // Prefer the system google-chrome that already renders PDFs from this repo.
  const candidates = [
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

async function main() {
  const [htmlPath, outPath] = process.argv.slice(2);
  if (!htmlPath || !outPath) {
    console.error('Usage: node fit_check.js <html_path> <output_json_path>');
    process.exit(2);
  }
  const absHtml = path.resolve(htmlPath);
  if (!fs.existsSync(absHtml)) {
    console.error(`HTML not found: ${absHtml}`);
    process.exit(2);
  }

  const chromePath = findChromePath();
  if (!chromePath) {
    console.error('No system Chrome found at standard paths.');
    process.exit(3);
  }

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport(VIEWPORT);
    // Print-media emulation makes the browser apply the same @media print
    // CSS rules + mm/cm unit handling that Chrome's PDF renderer uses —
    // produces measurements much closer to the actual PDF output than
    // screen mode (where browser zoom + box-shadow margins shift layout).
    await page.emulateMediaType('print');
    await page.goto(`file://${absHtml}`, { waitUntil: 'networkidle0', timeout: 60000 });

    // Brief settle for any late-loaded fonts/images
    await new Promise(r => setTimeout(r, 600));

    const measurements = await page.evaluate(() => {
      // `.page` clips content with `overflow: hidden`. We toggle to visible
      // briefly to measure how far below the page's bottom edge the natural
      // content actually extends. This preserves the flex layout (so the
      // footer stays at margin-top:auto, intermediate content keeps its
      // intended sizing) — we just allow the bottom of the layout to escape
      // the box so we can see how far past the page edge it goes.
      const nodes = Array.from(document.querySelectorAll('[data-section]'));
      return nodes.map((el, idx) => {
        const pad = el.querySelector('.page-pad') || el;
        const pageRect = el.getBoundingClientRect();
        const pageClient = el.clientHeight;

        const prevOverflow = el.style.overflow;
        const prevPadHeight = pad.style.height;
        el.style.overflow = 'visible';
        pad.style.height = 'auto';

        // Measure the bottom of the last visible child of .page-pad — that's
        // the page-footer in the normal layout. If its bottom exceeds pageRect.bottom,
        // the content overflowed.
        let lastChildBottom = pageRect.top;
        const children = Array.from(pad.children);
        for (const c of children) {
          const r = c.getBoundingClientRect();
          if (r.bottom > lastChildBottom) lastChildBottom = r.bottom;
        }
        const naturalContentHeight = lastChildBottom - pageRect.top;

        el.style.overflow = prevOverflow;
        pad.style.height = prevPadHeight;

        // Tiered overflow status. Browser layout in print-emulation mode is
        // consistently more conservative than the actual Chrome PDF render —
        // small overflows (<50px) are virtually always fine in the rendered
        // PDF, moderate overflows (50-200px) are worth watching, and large
        // overflows (>200px) almost certainly clip in the PDF too.
        const overflowPx = Math.max(0, naturalContentHeight - pageClient);
        let status;
        if (overflowPx <= 50) status = 'ok';
        else if (overflowPx <= 200) status = 'tight';
        else status = 'overflow';

        return {
          section_key: el.getAttribute('data-section'),
          page_index: idx + 1,
          client_height_px: pageClient,
          scroll_height_px: Math.round(naturalContentHeight),
          overflow_px: Math.round(overflowPx),
          status,
          overflow: status === 'overflow',
        };
      });
    });

    const report = {
      html_path: absHtml,
      viewport: VIEWPORT,
      sections: measurements,
      summary: {
        sections_measured: measurements.length,
        tight: measurements.filter(m => m.status === 'tight').length,
        overflows: measurements.filter(m => m.status === 'overflow').length,
      },
    };

    fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
    process.stdout.write(
      `${report.summary.sections_measured} sections measured · ` +
      `${report.summary.tight} tight · ` +
      `${report.summary.overflows} overflow\n`
    );
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error(err.stack || err.message || err);
  process.exit(1);
});
