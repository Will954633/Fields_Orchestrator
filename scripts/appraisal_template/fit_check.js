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
      // Scan every .page div in the document (not just templated [data-section]
      // ones) so that hard-coded pages like the inside cover and TOC are also
      // checked. For each: measure content overflow + footer Y position.
      // The footer baseline is determined by `.page-footer` (standard pages),
      // `.ic-bottom` (inside cover), or — as a last resort — the bottom of
      // the page-pad's last child. This catches any page whose bottom block
      // drifts from the standard baseline.
      const nodes = Array.from(document.querySelectorAll('.page'));
      return nodes.map((el, idx) => {
        const pad = el.querySelector('.page-pad, .inside-cover, .thesis-page-pad') || el;
        const pageRect = el.getBoundingClientRect();
        const pageClient = el.clientHeight;

        // Identify the bottom "anchor" element used to measure footer Y.
        // Priority: .page-footer > .ic-bottom > last visible child of pad.
        let anchorEl = el.querySelector('.page-footer')
                    || el.querySelector('.ic-bottom');
        let anchorKind = anchorEl?.classList.contains('page-footer') ? 'page-footer'
                       : anchorEl?.classList.contains('ic-bottom') ? 'ic-bottom'
                       : 'last-child-fallback';
        if (!anchorEl) {
          const kids = Array.from(pad.children).filter(c => c.getBoundingClientRect().height > 0);
          anchorEl = kids[kids.length - 1] || null;
        }
        let footerBottomFromPageTopPx = null;
        if (anchorEl) {
          const aR = anchorEl.getBoundingClientRect();
          footerBottomFromPageTopPx = Math.round(aR.bottom - pageRect.top);
        }

        // Toggle overflow:visible + page-pad height:auto so we can measure
        // the natural content stack size without clipping.
        const prevOverflow = el.style.overflow;
        const prevPadHeight = pad.style.height;
        el.style.overflow = 'visible';
        pad.style.height = 'auto';

        let lastChildBottom = pageRect.top;
        const children = Array.from(pad.children);
        for (const c of children) {
          const r = c.getBoundingClientRect();
          if (r.bottom > lastChildBottom) lastChildBottom = r.bottom;
        }
        const naturalContentHeight = lastChildBottom - pageRect.top;

        el.style.overflow = prevOverflow;
        pad.style.height = prevPadHeight;

        const overflowPx = Math.max(0, naturalContentHeight - pageClient);
        const clearancePx = pageClient - naturalContentHeight;
        let status;
        if (clearancePx >= 30) status = 'ok';            // ≥30px breathing room
        else if (overflowPx <= 50) status = 'tight';     // close to edge or 1-50px over
        else status = 'overflow';                        // >50px over the page

        return {
          section_key: el.getAttribute('data-section') || `page_${idx + 1}`,
          page_index: idx + 1,
          variant: el.getAttribute('data-variant') || 'standard',
          client_height_px: pageClient,
          scroll_height_px: Math.round(naturalContentHeight),
          overflow_px: Math.round(overflowPx),
          status,
          overflow: status === 'overflow',
          footer_bottom_px: footerBottomFromPageTopPx,
          footer_anchor: anchorKind,
        };
      });
    });

    // Cross-page footer alignment check. The footer should sit at the same Y
    // on every page (page-pad bottom padding is the only thing that moves it).
    // Determine the expected position from the mode of measured footer-Ys,
    // then flag any page whose footer drifts by more than `FOOTER_TOLERANCE_PX`.
    const FOOTER_TOLERANCE_PX = 6;  // ≈ 1.5mm tolerance
    const footerYs = measurements
      .map(m => m.footer_bottom_px)
      .filter(v => v !== null);
    let footerExpectedPx = null;
    let footerMisaligned = [];
    if (footerYs.length) {
      // Use the most common Y (mode) — handles the case where one page is wrong
      // and the majority are correct.
      const counts = new Map();
      for (const y of footerYs) counts.set(y, (counts.get(y) || 0) + 1);
      footerExpectedPx = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
      footerMisaligned = measurements
        .filter(m => m.footer_bottom_px !== null &&
                     Math.abs(m.footer_bottom_px - footerExpectedPx) > FOOTER_TOLERANCE_PX)
        .map(m => ({
          section_key: m.section_key,
          variant: m.variant,
          footer_bottom_px: m.footer_bottom_px,
          drift_px: m.footer_bottom_px - footerExpectedPx,
        }));
    }

    const report = {
      html_path: absHtml,
      viewport: VIEWPORT,
      sections: measurements,
      footer_alignment: {
        expected_bottom_px: footerExpectedPx,
        tolerance_px: FOOTER_TOLERANCE_PX,
        misaligned: footerMisaligned,
      },
      summary: {
        sections_measured: measurements.length,
        tight: measurements.filter(m => m.status === 'tight').length,
        overflows: measurements.filter(m => m.status === 'overflow').length,
        footer_misaligned: footerMisaligned.length,
      },
    };

    fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
    process.stdout.write(
      `${report.summary.sections_measured} sections measured · ` +
      `${report.summary.tight} tight · ` +
      `${report.summary.overflows} overflow · ` +
      `${report.summary.footer_misaligned} footer-misaligned\n`
    );
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error(err.stack || err.message || err);
  process.exit(1);
});
