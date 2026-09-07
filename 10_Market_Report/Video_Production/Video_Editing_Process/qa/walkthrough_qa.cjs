/*
 * walkthrough_qa.cjs — headless QA/lint harness for the "Walkthrough with Will" on-page video overlay.
 *
 * USAGE:
 *   NODE_PATH=/home/fields/Feilds_Website/01_Website/node_modules node walkthrough_qa.cjs \
 *     [baseUrl] [--out DIR] [--generatedAt STR] [--timepoints "10,27,..."]
 *   Defaults: baseUrl=https://fieldsestate.com.au/news/robina?walkthrough=1, out=qa/out (relative to cwd).
 *   Runs desktop 1280x1024 + mobile 390x844 across the audit timepoints, screenshots every lint
 *   violation, writes <out>/qa_report.json, prints a summary. Exit 1 if any findings, 0 if clean.
 */
'use strict';

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

// ---- argv ----
const argv = process.argv.slice(2);
let baseUrl = 'https://fieldsestate.com.au/news/robina?walkthrough=1';
let outDir = null; // default: <script dir>/out
let generatedAt = 'fixed-run';
let timepoints = [10, 27, 33, 40, 47, 52, 60, 88, 112, 118, 124, 131, 138, 154, 162, 168,
  173, 178, 184, 190, 196, 202, 234, 240, 248, 254, 262, 268, 283, 289, 296, 302, 324,
  330, 340, 352, 366, 372, 382, 400, 406, 412, 418, 424, 511, 517, 522, 546, 552, 581,
  589, 597, 605, 620, 628];

for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--out') { outDir = argv[++i]; }
  else if (a === '--generatedAt') { generatedAt = argv[++i]; }
  else if (a === '--timepoints') { timepoints = argv[++i].split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n)); }
  else if (!a.startsWith('--')) { baseUrl = a; }
}

outDir = outDir ? path.resolve(process.cwd(), outDir) : path.join(__dirname, 'out');
fs.mkdirSync(outDir, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 1024, deviceScaleFactor: 1, isMobile: false, hasTouch: false, navConst: 64 },
  { name: 'mobile', width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true, navConst: 56 },
];

const MAX_SHOTS = 40;
let shotCount = 0;
const shotKeys = new Set(); // dedup rule+viewport+element

const findings = [];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ---- geometry helpers (run in Node) ----
function interArea(a, b) {
  const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return x * y;
}
function area(r) { return Math.max(0, r.right - r.left) * Math.max(0, r.bottom - r.top); }
function centerIn(r, box) {
  const cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
  return cx >= box.left && cx <= box.right && cy >= box.top && cy <= box.bottom;
}

// The in-page collector: returns raw geometry, no lint logic.
function collectInPage() {
  const rect = el => {
    const r = el.getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
  };
  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    return true;
  };
  const txt = el => (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);

  const cap = document.getElementById('wkCap');
  const capVisible = cap && !cap.classList.contains('hide') && visible(cap);

  // nav bottom detection
  let navBottom = null;
  const navSel = ['header nav', 'nav', 'header', '[role="navigation"]'];
  for (const s of navSel) {
    const n = document.querySelector(s);
    if (n) {
      const r = n.getBoundingClientRect();
      if (r.top <= 2 && r.height > 0 && r.height < 160) { navBottom = r.bottom; break; }
    }
  }

  const notes = [...document.querySelectorAll('.wk-note')].filter(visible).map(el => ({ rect: rect(el), text: txt(el) }));
  const boxlines = [...document.querySelectorAll('.wk-boxline')].filter(visible).map(el => ({ rect: rect(el), text: txt(el) }));
  const noteboxes = [...document.querySelectorAll('.wk-notebox')].filter(visible).map(el => ({ rect: rect(el), text: txt(el) }));
  const hls = [...document.querySelectorAll('.wk-hl')].filter(visible).map(el => ({ rect: rect(el) }));
  const paths = [...document.querySelectorAll('#wkInk path')].filter(visible).map(el => ({
    rect: rect(el),
    stroke: (el.getAttribute('stroke') || getComputedStyle(el).stroke || '').toLowerCase(),
  }));
  const charts = [...document.querySelectorAll('svg.chart-svg')].filter(visible).map(el => rect(el));

  return {
    capVisible: !!capVisible,
    capRect: cap ? rect(cap) : null,
    navBottom,
    notes, boxlines, noteboxes, hls, paths, charts,
    viewportW: window.innerWidth, viewportH: window.innerHeight,
  };
}

function isRedCircle(p) {
  const s = (p.stroke || '');
  const red = s.includes('#dc3545') || s.includes('220, 53, 69') || s.includes('220,53,69');
  if (!red) return false;
  const w = p.rect.width, h = p.rect.height;
  if (!(w > 20 && h > 20)) return false;
  const ar = w / h;
  return ar >= 0.4 && ar <= 2.5;
}

async function lintPoint(vp, t, data, page) {
  const navBottom = (data.navBottom != null ? data.navBottom : vp.navConst);
  const vw = data.viewportW || vp.width;
  const local = [];
  const add = (rule, detail, elementText) => local.push({ viewport: vp.name, t, rule, detail, elementText: elementText || '' });

  // 1. offscreen — .wk-note / .wk-boxline / .wk-notebox
  const offCandidates = [
    ...data.notes.map(n => ({ ...n, kind: 'wk-note' })),
    ...data.boxlines.map(n => ({ ...n, kind: 'wk-boxline' })),
    ...data.noteboxes.map(n => ({ ...n, kind: 'wk-notebox' })),
  ];
  for (const c of offCandidates) {
    const r = c.rect;
    if (r.left < 0 || r.right > vw || r.left < 4) {
      add('offscreen', `${c.kind} left=${r.left.toFixed(0)} right=${r.right.toFixed(0)} vw=${vw}`, c.text);
    }
  }

  // 2. over-nav — .wk-note or ink path with top < navBottom
  for (const n of data.notes) {
    if (n.rect.top < navBottom) add('over-nav', `wk-note top=${n.rect.top.toFixed(0)} navBottom=${navBottom.toFixed(0)}`, n.text);
  }
  for (const p of data.paths) {
    if (p.rect.top < navBottom) add('over-nav', `ink path top=${p.rect.top.toFixed(0)} navBottom=${navBottom.toFixed(0)} stroke=${p.stroke}`, '');
  }

  // 3. over-caption
  if (data.capVisible && data.capRect) {
    for (const c of offCandidates) {
      if (interArea(c.rect, data.capRect) > 0) {
        add('over-caption', `${c.kind} intersects caption area=${interArea(c.rect, data.capRect).toFixed(0)}`, c.text);
      }
    }
  }

  // 4. note-overlap — wk-note vs wk-note, and wk-note vs wk-boxline (>30% of smaller)
  const olA = data.notes.map(n => ({ ...n, kind: 'wk-note' }));
  const olB = data.boxlines.map(n => ({ ...n, kind: 'wk-boxline' }));
  const pairs = [];
  for (let i = 0; i < olA.length; i++) for (let j = i + 1; j < olA.length; j++) pairs.push([olA[i], olA[j]]);
  for (const a of olA) for (const b of olB) pairs.push([a, b]);
  for (const [a, b] of pairs) {
    const ia = interArea(a.rect, b.rect);
    if (ia <= 0) continue;
    const smaller = Math.min(area(a.rect), area(b.rect));
    if (smaller > 0 && ia / smaller > 0.30) {
      add('note-overlap', `${a.kind}("${a.text}") vs ${b.kind}("${b.text}") overlap=${(100 * ia / smaller).toFixed(0)}%`, a.text);
    }
  }

  // 5. note-on-circle
  const circles = data.paths.filter(isRedCircle);
  for (const n of data.notes) {
    for (const c of circles) {
      if (centerIn(n.rect, c.rect)) {
        add('note-on-circle', `wk-note center inside red circle bbox (${c.rect.width.toFixed(0)}x${c.rect.height.toFixed(0)})`, n.text);
        break;
      }
    }
  }

  // 6. stale-ink / off-paper — ink path OR wk-note entirely outside every chart+70px, and below navBottom
  const M = 70;
  const outsideAllCharts = r => {
    for (const ch of data.charts) {
      const ex = { left: ch.left - M, top: ch.top - M, right: ch.right + M, bottom: ch.bottom + M };
      if (interArea(r, ex) > 0) return false; // intersects an expanded chart -> not off-paper
    }
    return true;
  };
  const staleCandidates = [
    ...data.paths.map(p => ({ rect: p.rect, kind: 'ink path', text: '' })),
    // exclude the entrance settings asterisks ("*"): they intentionally sit ON the settings pills,
    // which are above the chart svg — legitimately "off chart", not ink left behind from a prior scene.
    ...data.notes.filter(n => n.text !== '*').map(n => ({ rect: n.rect, kind: 'wk-note', text: n.text })),
  ];
  for (const c of staleCandidates) {
    if (c.rect.top >= navBottom && data.charts.length > 0 && outsideAllCharts(c.rect)) {
      add('stale-ink', `${c.kind} floating off all charts (top=${c.rect.top.toFixed(0)})`, c.text);
    }
  }

  // screenshots (deduped + capped)
  for (const f of local) {
    findings.push(f);
    const dedupKey = `${f.rule}|${f.viewport}|${(f.elementText || '').slice(0, 30)}`;
    if (shotCount >= MAX_SHOTS || shotKeys.has(dedupKey)) continue;
    shotKeys.add(dedupKey);
    const name = `v${vp.width}_t${t}_${f.rule}.png`;
    try {
      await page.screenshot({ path: path.join(outDir, name), fullPage: true });
      shotCount++;
    } catch (e) { /* ignore screenshot errors */ }
  }
  return local.length;
}

async function seekTo(page, t) {
  await page.evaluate((T) => {
    const v = document.getElementById('wkVid');
    if (v) { v.pause(); v.currentTime = T; }
  }, t);
  await sleep(1800);
  // re-pin (rAF may nudge it)
  await page.evaluate((T) => {
    const v = document.getElementById('wkVid');
    if (v) { v.pause(); v.currentTime = T; }
  }, t);
  await sleep(250);
}

async function runViewport(browser, vp) {
  const page = await browser.newPage();
  await page.setViewport({
    width: vp.width, height: vp.height, deviceScaleFactor: vp.deviceScaleFactor,
    isMobile: vp.isMobile, hasTouch: vp.hasTouch,
  });
  page.setDefaultNavigationTimeout(60000);
  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle2', timeout: 60000 });
  } catch (e) {
    console.error(`[${vp.name}] navigation issue: ${e.message} — continuing`);
  }
  await sleep(2000);

  // start the walkthrough
  try {
    await page.waitForSelector('[data-tour="play"]', { timeout: 15000 });
    await page.click('[data-tour="play"]');
  } catch (e) {
    console.error(`[${vp.name}] could not click play: ${e.message}`);
  }
  await sleep(2500);
  // ensure video is present
  const hasVid = await page.evaluate(() => !!document.getElementById('wkVid'));
  if (!hasVid) console.error(`[${vp.name}] WARNING: #wkVid not found after play`);

  for (const t of timepoints) {
    try {
      await seekTo(page, t);
      const data = await page.evaluate(collectInPage);
      const n = await lintPoint(vp, t, data, page);
      if (n) process.stdout.write(`  [${vp.name}] t=${t}: ${n} finding(s)\n`);
    } catch (e) {
      console.error(`  [${vp.name}] t=${t} ERROR: ${e.message}`);
    }
  }
  await page.close();
}

(async () => {
  console.log(`walkthrough_qa: ${baseUrl}`);
  console.log(`out: ${outDir}`);
  for (const vp of VIEWPORTS) {
    console.log(`\n=== viewport ${vp.name} ${vp.width}x${vp.height} ===`);
    const browser = await puppeteer.launch({
      headless: 'new',
      executablePath: '/usr/bin/google-chrome',
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });
    try {
      await runViewport(browser, vp);
    } catch (e) {
      console.error(`[${vp.name}] fatal: ${e.message}`);
    } finally {
      await browser.close();
    }
  }

  // counts per rule
  const counts = {};
  for (const f of findings) counts[f.rule] = (counts[f.rule] || 0) + 1;

  const report = { generatedAt, baseUrl, findings, counts, total: findings.length, screenshots: shotCount };
  fs.writeFileSync(path.join(outDir, 'qa_report.json'), JSON.stringify(report, null, 2));

  console.log('\n===== SUMMARY =====');
  console.log(`total findings: ${findings.length}`);
  for (const [r, c] of Object.entries(counts).sort((a, b) => b[1] - a[1])) console.log(`  ${r}: ${c}`);
  console.log(`screenshots written: ${shotCount}`);
  console.log(`report: ${path.join(outDir, 'qa_report.json')}`);

  process.exit(findings.length > 0 ? 1 : 0);
})();
