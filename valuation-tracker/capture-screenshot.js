#!/usr/bin/env node
/**
 * Domain.com.au Property Valuation Screenshot Capture
 *
 * Takes screenshots of Domain property profile pages to document
 * their automated valuation estimates before and after listing.
 *
 * Supports Bright Data rotating residential proxies.
 *
 * Usage:
 *   node capture-screenshot.js --url <property-profile-url> --output <dir> --label <before|after>
 *   node capture-screenshot.js --address "28 Federal Place, Robina, QLD 4226" --output <dir> --label <before|after>
 *   node capture-screenshot.js --batch <json-file>   # Batch mode: [{address, outputDir, label}, ...]
 */

const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

// Load .env from the valuation-tracker directory
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf-8').split('\n')) {
        const match = line.match(/^([A-Z_]+)=(.+)$/);
        if (match && !process.env[match[1]]) {
            process.env[match[1]] = match[2].trim();
        }
    }
}

const CHROME_PATH = '/usr/bin/google-chrome';
const DEFAULT_TIMEOUT = 60000;
const VIEWPORT = { width: 1440, height: 900 };

function parseArgs() {
    const args = process.argv.slice(2);
    const parsed = {};
    for (let i = 0; i < args.length; i++) {
        if (args[i].startsWith('--')) {
            const key = args[i].slice(2);
            parsed[key] = args[i + 1] || true;
            i++;
        }
    }
    return parsed;
}

function addressToSlug(address) {
    return address
        .toLowerCase()
        .replace(/,/g, '')
        .replace(/\s+/g, '-')
        .replace(/[^a-z0-9-]/g, '');
}

function addressToProfileUrl(address) {
    return `https://www.domain.com.au/property-profile/${addressToSlug(address)}`;
}

function buildProxyArgs() {
    const host = process.env.BRIGHT_DATA_HOST;
    const port = process.env.BRIGHT_DATA_PORT || '22225';
    const username = process.env.BRIGHT_DATA_USERNAME;
    const password = process.env.BRIGHT_DATA_PASSWORD;

    if (!host || !username || !password) {
        return { launchArg: null, auth: null };
    }

    return {
        launchArg: `--proxy-server=http://${host}:${port}`,
        auth: { username, password },
    };
}

function extractValuationFromText(text) {
    const result = {
        estimateLow: null,
        estimateMid: null,
        estimateHigh: null,
        accuracy: null,
        updatedDate: null,
        isForSale: false,
        rentalEstimate: null,
        rentalYield: null,
    };

    // Extract LOW / MID / HIGH values
    // Pattern: "LOW\n$1.72m\nMID\n$2m\nHIGH\n$2.28m" or "LOW\n\n$1.72M\n\nMID\n\n$2M\n\nHIGH\n\n$2.28M"
    const lowMatch = text.match(/LOW\s*\n?\s*\$?([\d,.]+[kmKM]?)/i);
    const midMatch = text.match(/MID\s*\n?\s*\$?([\d,.]+[kmKM]?)/i);
    const highMatch = text.match(/HIGH\s*\n?\s*\$?([\d,.]+[kmKM]?)/i);

    if (lowMatch) result.estimateLow = '$' + lowMatch[1];
    if (midMatch) result.estimateMid = '$' + midMatch[1];
    if (highMatch) result.estimateHigh = '$' + highMatch[1];

    // Accuracy: "High accuracy" or "rated high"
    const accMatch = text.match(/(?:rated\s+|accuracy[:\s]*)(high|medium|low)/i);
    if (accMatch) result.accuracy = accMatch[1].toLowerCase();

    // Updated date: "Updated: 02 Mar, 2026"
    const dateMatch = text.match(/Updated:\s*(\d{1,2}\s+\w+,?\s*\d{4})/i);
    if (dateMatch) result.updatedDate = dateMatch[1];

    // Is for sale?
    result.isForSale = /currently\s+(?:for\s+sale|listed)/i.test(text);

    // Rental estimate
    const rentalMatch = text.match(/PER\s+WEEK\s*\n?\s*\$?([\d,]+)/i);
    if (rentalMatch) result.rentalEstimate = '$' + rentalMatch[1] + '/week';

    // Rental yield
    const yieldMatch = text.match(/([\d.]+)%\s*Rental\s*yield/i);
    if (yieldMatch) result.rentalYield = yieldMatch[1] + '%';

    return result;
}

async function captureValuation(browser, url, outputDir, label) {
    const page = await browser.newPage();

    try {
        // Set proxy auth if configured
        const proxy = buildProxyArgs();
        if (proxy.auth) {
            await page.authenticate(proxy.auth);
        }

        await page.setViewport(VIEWPORT);
        await page.setUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        );

        console.log(`[capture] Navigating to: ${url}`);
        await page.goto(url, { waitUntil: 'networkidle2', timeout: DEFAULT_TIMEOUT });
        await new Promise(r => setTimeout(r, 3000));

        fs.mkdirSync(outputDir, { recursive: true });

        // Take full page screenshot
        const fullPath = path.join(outputDir, `${label}-full.png`);
        await page.screenshot({ path: fullPath, fullPage: true });
        console.log(`[capture] Full screenshot: ${fullPath}`);

        // Extract page text and parse valuation
        const pageData = await page.evaluate(() => {
            return {
                title: document.title,
                text: document.body.innerText,
            };
        });

        const valuation = extractValuationFromText(pageData.text);

        // Screenshot the valuation section of the page
        let valuationScreenshot = null;
        try {
            // Scroll to the "Property value" section and take a viewport screenshot
            await page.evaluate(() => {
                const headings = document.querySelectorAll('h2, h3, h4');
                for (const h of headings) {
                    if (/property\s*value/i.test(h.textContent)) {
                        h.scrollIntoView({ block: 'start', behavior: 'instant' });
                        window.scrollBy(0, -80); // Small offset above
                        return;
                    }
                }
                // Fallback: scroll to the estimate range area
                const est = document.querySelector('[data-testid*="estimate"]');
                if (est) {
                    est.scrollIntoView({ block: 'start', behavior: 'instant' });
                    window.scrollBy(0, -80);
                }
            });

            await new Promise(r => setTimeout(r, 500));

            const valPath = path.join(outputDir, `${label}-valuation.png`);
            await page.screenshot({ path: valPath }); // viewport screenshot (not fullPage)
            valuationScreenshot = valPath;
            console.log(`[capture] Valuation screenshot: ${valPath}`);
        } catch (e) {
            console.log(`[capture] Valuation section screenshot failed: ${e.message}`);
        }

        // Save structured data
        const captureData = {
            url,
            label,
            capturedAt: new Date().toISOString(),
            proxyUsed: !!buildProxyArgs().auth,
            valuation,
            pageTitle: pageData.title,
            screenshots: {
                full: path.basename(fullPath),
                valuation: valuationScreenshot ? path.basename(valuationScreenshot) : null,
            },
        };

        const dataPath = path.join(outputDir, `${label}-data.json`);
        fs.writeFileSync(dataPath, JSON.stringify(captureData, null, 2));

        console.log(`[capture] ✓ ${valuation.estimateMid || 'no estimate'} (${valuation.accuracy || 'unknown'} accuracy, ${valuation.isForSale ? 'FOR SALE' : 'not listed'})`);

        return captureData;
    } finally {
        await page.close();
    }
}

async function main() {
    const args = parseArgs();

    // Build browser launch args
    const proxy = buildProxyArgs();
    const launchArgs = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
    ];

    // Bright Data proxy uses its own SSL certificate — must ignore cert errors when proxied
    if (proxy.launchArg) {
        launchArgs.push('--ignore-certificate-errors');
    }
    if (proxy.launchArg) launchArgs.push(proxy.launchArg);

    console.log(`[capture] Launching browser${proxy.auth ? ' with Bright Data proxy' : ' (no proxy)'}...`);

    const browser = await puppeteer.launch({
        executablePath: CHROME_PATH,
        headless: 'new',
        args: launchArgs,
        timeout: DEFAULT_TIMEOUT,
    });

    try {
        if (args.batch) {
            // Batch mode: read JSON array of {address, outputDir, label}
            const tasks = JSON.parse(fs.readFileSync(args.batch, 'utf-8'));
            console.log(`[batch] Processing ${tasks.length} properties...`);

            const results = [];
            for (let i = 0; i < tasks.length; i++) {
                const task = tasks[i];
                const url = task.url || addressToProfileUrl(task.address);
                const outputDir = task.outputDir || `./screenshots/${addressToSlug(task.address)}`;
                const label = task.label || 'snapshot';

                console.log(`\n[batch] ${i + 1}/${tasks.length}: ${task.address || url}`);
                try {
                    const result = await captureValuation(browser, url, outputDir, label);
                    results.push({ ...result, address: task.address, success: true });
                } catch (err) {
                    console.error(`[batch] FAILED: ${err.message}`);
                    results.push({ address: task.address, url, success: false, error: err.message });
                }

                // Delay between captures to be polite / avoid rate limiting
                if (i < tasks.length - 1) {
                    const delay = 3000 + Math.random() * 4000; // 3-7 seconds
                    await new Promise(r => setTimeout(r, delay));
                }
            }

            // Write batch summary
            const summaryPath = args.output || './screenshots/batch-summary.json';
            fs.mkdirSync(path.dirname(summaryPath), { recursive: true });
            fs.writeFileSync(summaryPath, JSON.stringify(results, null, 2));
            console.log(`\n[batch] Summary written to: ${summaryPath}`);
            console.log(`[batch] ${results.filter(r => r.success).length}/${results.length} successful`);

        } else {
            // Single capture mode
            if (!args.url && !args.address) {
                console.error('Usage:');
                console.error('  node capture-screenshot.js --address "28 Federal Place, Robina, QLD 4226" --output <dir> --label <before|after>');
                console.error('  node capture-screenshot.js --url <property-profile-url> --output <dir> --label <before|after>');
                console.error('  node capture-screenshot.js --batch <tasks.json>');
                process.exit(1);
            }

            const url = args.url || addressToProfileUrl(args.address);
            const outputDir = args.output || `./valuation-tracker/screenshots/${addressToSlug(args.address || 'capture')}`;
            const label = args.label || 'snapshot';

            await captureValuation(browser, url, outputDir, label);
        }
    } finally {
        await browser.close();
    }
}

module.exports = { captureValuation, addressToProfileUrl, addressToSlug, extractValuationFromText };
main();
