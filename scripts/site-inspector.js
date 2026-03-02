#!/usr/bin/env node
/**
 * site-inspector.js — Visual inspection tool for Fields Estate website
 *
 * Takes full-page screenshots, captures console logs, network errors,
 * and page text from any page on fieldsestate.com.au.
 *
 * Claude reads the output PNGs (multimodal vision) and text files
 * to verify visual rendering after deploys.
 *
 * Usage:
 *   node scripts/site-inspector.js --url https://fieldsestate.com.au/for-sale
 *   node scripts/site-inspector.js --url /for-sale                          # shorthand
 *   node scripts/site-inspector.js --url /for-sale --mobile
 *   node scripts/site-inspector.js --url /for-sale --element ".property-card"
 *   node scripts/site-inspector.js --url /for-sale,/market,/ops             # multiple pages
 *   node scripts/site-inspector.js --url /for-sale --wait 5000              # extra wait ms
 *   node scripts/site-inspector.js --url /for-sale --no-screenshot          # text + console only
 */

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'https://fieldsestate.com.au';
const CHROME_PATH = '/usr/bin/google-chrome';
const OUTPUT_DIR = '/tmp/site-inspect';

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 375, height: 812 },
};

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    urls: [],
    viewport: 'desktop',
    element: null,
    wait: 2000,
    screenshot: true,
    fullPage: true,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--url':
        opts.urls = args[++i].split(',').map(u => {
          u = u.trim();
          if (u.startsWith('/')) u = BASE_URL + u;
          if (!u.startsWith('http')) u = BASE_URL + '/' + u;
          return u;
        });
        break;
      case '--mobile':
        opts.viewport = 'mobile';
        break;
      case '--tablet':
        opts.viewport = 'tablet';
        break;
      case '--element':
        opts.element = args[++i];
        break;
      case '--wait':
        opts.wait = parseInt(args[++i], 10);
        break;
      case '--no-screenshot':
        opts.screenshot = false;
        break;
      case '--no-full-page':
        opts.fullPage = false;
        break;
      case '--help':
        console.log(`
site-inspector.js — Visual inspection for fieldsestate.com.au

Options:
  --url <url[,url2,...]>  Page(s) to inspect. Paths like /for-sale are expanded.
  --mobile                Use mobile viewport (375x812)
  --tablet                Use tablet viewport (768x1024)
  --element <selector>    Screenshot a specific CSS element
  --wait <ms>             Extra wait after load (default: 2000)
  --no-screenshot         Skip screenshot, capture text + console only
  --no-full-page          Viewport-only screenshot (not full scrollable page)
  --help                  Show this help

Output goes to /tmp/site-inspect/<slug>/
  screenshot.png          Full page screenshot
  screenshot-mobile.png   If --mobile
  console.log             All console output
  network-errors.log      Failed requests (4xx, 5xx, blocked)
  page-text.txt           All visible text on the page
  page-info.json          Page metadata (title, URL, viewport, timing)
`);
        process.exit(0);
    }
  }

  if (opts.urls.length === 0) {
    console.error('Error: --url is required. Use --help for usage.');
    process.exit(1);
  }

  return opts;
}

function urlToSlug(url) {
  const u = new URL(url);
  let slug = u.pathname.replace(/^\//, '').replace(/\//g, '_') || 'home';
  return slug.substring(0, 80);
}

async function inspectPage(browser, url, opts) {
  const slug = urlToSlug(url);
  const outDir = path.join(OUTPUT_DIR, slug);
  fs.mkdirSync(outDir, { recursive: true });

  const suffix = opts.viewport !== 'desktop' ? `-${opts.viewport}` : '';
  const consoleLogs = [];
  const networkErrors = [];

  const page = await browser.newPage();
  const viewport = VIEWPORTS[opts.viewport];
  await page.setViewport(viewport);

  // Capture console messages
  page.on('console', msg => {
    const type = msg.type().toUpperCase();
    const text = msg.text();
    const ts = new Date().toISOString();
    consoleLogs.push(`[${ts}] [${type}] ${text}`);
  });

  // Capture page errors (uncaught exceptions)
  page.on('pageerror', err => {
    const ts = new Date().toISOString();
    consoleLogs.push(`[${ts}] [PAGEERROR] ${err.message}`);
  });

  // Capture network failures
  page.on('requestfailed', req => {
    networkErrors.push({
      url: req.url(),
      method: req.method(),
      failure: req.failure()?.errorText || 'unknown',
      resourceType: req.resourceType(),
    });
  });

  // Capture HTTP errors (4xx, 5xx)
  page.on('response', resp => {
    if (resp.status() >= 400) {
      networkErrors.push({
        url: resp.url(),
        status: resp.status(),
        statusText: resp.statusText(),
        resourceType: resp.request().resourceType(),
      });
    }
  });

  const startTime = Date.now();

  try {
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
  } catch (err) {
    consoleLogs.push(`[NAVIGATION ERROR] ${err.message}`);
    // Continue — partial load may still be useful
  }

  // Extra wait for dynamic content (charts, lazy images)
  if (opts.wait > 0) {
    await new Promise(r => setTimeout(r, opts.wait));
  }

  const loadTime = Date.now() - startTime;

  // Get page title
  const title = await page.title();

  // Full-page screenshot
  if (opts.screenshot) {
    const screenshotPath = path.join(outDir, `screenshot${suffix}.png`);
    if (opts.element) {
      const el = await page.$(opts.element);
      if (el) {
        await el.screenshot({ path: screenshotPath });
      } else {
        consoleLogs.push(`[INSPECTOR] Element not found: ${opts.element}`);
        await page.screenshot({ path: screenshotPath, fullPage: opts.fullPage });
      }
    } else {
      await page.screenshot({ path: screenshotPath, fullPage: opts.fullPage });
    }
  }

  // Extract all visible text
  const pageText = await page.evaluate(() => {
    const walk = (node, depth = 0) => {
      const lines = [];
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent.trim();
        if (text) lines.push(text);
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = node.tagName.toLowerCase();
        const style = window.getComputedStyle(node);
        // Skip hidden elements
        if (style.display === 'none' || style.visibility === 'hidden') return lines;
        // Skip script/style
        if (tag === 'script' || tag === 'style' || tag === 'noscript') return lines;

        // Add semantic markers
        if (['h1','h2','h3','h4','h5','h6'].includes(tag)) {
          lines.push(`\n${'#'.repeat(parseInt(tag[1]))} ${node.textContent.trim()}`);
          return lines;
        }
        if (tag === 'img') {
          const alt = node.getAttribute('alt') || '';
          const src = node.getAttribute('src') || '';
          lines.push(`[IMAGE: ${alt || src.split('/').pop()}]`);
          return lines;
        }
        if (tag === 'a') {
          const href = node.getAttribute('href') || '';
          const text = node.textContent.trim();
          if (text) lines.push(`[${text}](${href})`);
          return lines;
        }

        for (const child of node.childNodes) {
          lines.push(...walk(child, depth + 1));
        }

        if (['p','div','li','tr','section','article','header','footer','main'].includes(tag)) {
          lines.push('');
        }
      }
      return lines;
    };
    return walk(document.body).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  });

  // Write outputs
  fs.writeFileSync(path.join(outDir, `page-text${suffix}.txt`), pageText);

  if (consoleLogs.length > 0) {
    fs.writeFileSync(path.join(outDir, `console${suffix}.log`), consoleLogs.join('\n'));
  }

  if (networkErrors.length > 0) {
    fs.writeFileSync(
      path.join(outDir, `network-errors${suffix}.log`),
      networkErrors.map(e => JSON.stringify(e)).join('\n')
    );
  }

  const pageInfo = {
    url,
    title,
    viewport: `${viewport.width}x${viewport.height}`,
    viewportName: opts.viewport,
    loadTimeMs: loadTime,
    consoleMessages: consoleLogs.length,
    networkErrors: networkErrors.length,
    timestamp: new Date().toISOString(),
    outputDir: outDir,
    files: fs.readdirSync(outDir),
  };
  fs.writeFileSync(path.join(outDir, `page-info${suffix}.json`), JSON.stringify(pageInfo, null, 2));

  await page.close();
  return pageInfo;
}

async function main() {
  const opts = parseArgs();

  // Clean previous runs
  if (fs.existsSync(OUTPUT_DIR)) {
    fs.rmSync(OUTPUT_DIR, { recursive: true });
  }
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-extensions',
      '--window-size=1440,900',
    ],
  });

  const results = [];

  for (const url of opts.urls) {
    try {
      console.log(`Inspecting: ${url} (${opts.viewport})`);
      const info = await inspectPage(browser, url, opts);
      results.push(info);
      console.log(`  -> ${info.outputDir}/`);
      console.log(`     Title: ${info.title}`);
      console.log(`     Load: ${info.loadTimeMs}ms | Console: ${info.consoleMessages} msgs | Network errors: ${info.networkErrors}`);
      info.files.forEach(f => console.log(`     ${f}`));
    } catch (err) {
      console.error(`  ERROR inspecting ${url}: ${err.message}`);
      results.push({ url, error: err.message });
    }
  }

  await browser.close();

  // Write summary
  const summary = {
    inspectedAt: new Date().toISOString(),
    viewport: opts.viewport,
    pages: results,
  };
  fs.writeFileSync(path.join(OUTPUT_DIR, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(`\nDone. Output: ${OUTPUT_DIR}/`);
  console.log(`Summary: ${OUTPUT_DIR}/summary.json`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
