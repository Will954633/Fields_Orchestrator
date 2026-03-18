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
    actionsFile: null,
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
  --actions-file <path>   JSON file with scripted interactions to run after load
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
  action-log.json         Steps executed from --actions-file
`);
        process.exit(0);
      case '--actions-file':
        opts.actionsFile = args[++i];
        break;
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

function sanitizeArtifactName(name) {
  return String(name || 'snapshot')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .substring(0, 60) || 'snapshot';
}

function loadActions(actionsFile) {
  if (!actionsFile) return [];
  const raw = fs.readFileSync(actionsFile, 'utf8');
  const actions = JSON.parse(raw);
  if (!Array.isArray(actions)) {
    throw new Error('--actions-file must contain a JSON array of action objects');
  }
  return actions;
}

async function writePageText(page, filepath) {
  const pageText = await page.evaluate(() => {
    const walk = node => {
      const lines = [];
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent.trim();
        if (text) lines.push(text);
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = node.tagName.toLowerCase();
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') return lines;
        if (tag === 'script' || tag === 'style' || tag === 'noscript') return lines;

        if (['h1','h2','h3','h4','h5','h6'].includes(tag)) {
          lines.push(`\n${'#'.repeat(parseInt(tag[1], 10))} ${node.textContent.trim()}`);
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
          lines.push(...walk(child));
        }

        if (['p','div','li','tr','section','article','header','footer','main'].includes(tag)) {
          lines.push('');
        }
      }
      return lines;
    };
    return walk(document.body).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  });

  fs.writeFileSync(filepath, pageText);
}

async function captureArtifacts(page, outDir, opts, suffix, label = '') {
  const nameSuffix = label ? `-${sanitizeArtifactName(label)}` : '';

  if (opts.screenshot) {
    const screenshotPath = path.join(outDir, `screenshot${nameSuffix}${suffix}.png`);
    if (opts.element) {
      const el = await page.$(opts.element);
      if (el) {
        await el.screenshot({ path: screenshotPath });
      } else {
        throw new Error(`Element not found for screenshot selector: ${opts.element}`);
      }
    } else {
      await page.screenshot({ path: screenshotPath, fullPage: opts.fullPage });
    }
  }

  await writePageText(page, path.join(outDir, `page-text${nameSuffix}${suffix}.txt`));
}

async function runAction(page, action) {
  const type = action.type;
  switch (type) {
    case 'click':
      await page.waitForSelector(action.selector, { timeout: action.timeout || 10000 });
      await page.click(action.selector);
      break;
    case 'type':
      await page.waitForSelector(action.selector, { timeout: action.timeout || 10000 });
      if (action.clear !== false) {
        await page.$eval(action.selector, el => {
          el.value = '';
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        });
      }
      await page.type(action.selector, action.text || '', { delay: action.delay || 20 });
      break;
    case 'select':
      await page.waitForSelector(action.selector, { timeout: action.timeout || 10000 });
      await page.select(action.selector, action.value);
      break;
    case 'hover':
      await page.waitForSelector(action.selector, { timeout: action.timeout || 10000 });
      await page.hover(action.selector);
      break;
    case 'press':
      await page.keyboard.press(action.key);
      break;
    case 'wait':
      await new Promise(resolve => setTimeout(resolve, action.ms || 1000));
      break;
    case 'waitForSelector':
      await page.waitForSelector(action.selector, {
        timeout: action.timeout || 10000,
        visible: action.visible !== false,
      });
      break;
    case 'scroll':
      if (action.selector) {
        await page.waitForSelector(action.selector, { timeout: action.timeout || 10000 });
        await page.$eval(action.selector, el => {
          el.scrollIntoView({ behavior: 'instant', block: 'center' });
        });
      } else if (action.position === 'bottom') {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      } else {
        await page.evaluate(({ x, y }) => window.scrollBy(x || 0, y || 0), {
          x: action.x || 0,
          y: action.y || 800,
        });
      }
      break;
    case 'snapshot':
      break;
    default:
      throw new Error(`Unsupported action type: ${type}`);
  }
}

async function inspectPage(browser, url, opts) {
  const slug = urlToSlug(url);
  const outDir = path.join(OUTPUT_DIR, slug);
  fs.mkdirSync(outDir, { recursive: true });

  const suffix = opts.viewport !== 'desktop' ? `-${opts.viewport}` : '';
  const consoleLogs = [];
  const networkErrors = [];
  const actionLog = [];

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

  if (opts.actions.length > 0) {
    await captureArtifacts(page, outDir, opts, suffix, 'initial');
  }

  for (const action of opts.actions) {
    const startedAt = new Date().toISOString();
    const entry = {
      type: action.type,
      selector: action.selector || null,
      name: action.name || null,
      startedAt,
    };
    try {
      await runAction(page, action);
      if (action.postWaitMs) {
        await new Promise(resolve => setTimeout(resolve, action.postWaitMs));
      }
      if (action.type === 'snapshot') {
        await captureArtifacts(page, outDir, opts, suffix, action.name || 'snapshot');
      }
      entry.status = 'success';
      entry.finishedAt = new Date().toISOString();
    } catch (err) {
      entry.status = 'failed';
      entry.finishedAt = new Date().toISOString();
      entry.error = err.message;
      actionLog.push(entry);
      throw err;
    }
    actionLog.push(entry);
  }

  await captureArtifacts(page, outDir, opts, suffix);

  // Get page title
  const title = await page.title();

  if (consoleLogs.length > 0) {
    fs.writeFileSync(path.join(outDir, `console${suffix}.log`), consoleLogs.join('\n'));
  }

  if (networkErrors.length > 0) {
    fs.writeFileSync(
      path.join(outDir, `network-errors${suffix}.log`),
      networkErrors.map(e => JSON.stringify(e)).join('\n')
    );
  }

  if (actionLog.length > 0) {
    fs.writeFileSync(path.join(outDir, `action-log${suffix}.json`), JSON.stringify(actionLog, null, 2));
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
  opts.actions = loadActions(opts.actionsFile);

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
