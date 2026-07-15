#!/usr/bin/env node
/**
 * Domain Valuation Tracker — Laptop Capture Script
 *
 * Takes screenshots of Domain.com.au property profile pages to document
 * automated valuation estimates. Designed to run on a local machine with
 * a residential IP address.
 *
 * FULL RESUME CAPABILITY:
 *   - Progress is saved after every single capture to progress.json
 *   - If interrupted (Ctrl+C, crash, laptop closes), just run again
 *   - Automatically skips already-completed properties
 *   - Can be stopped and restarted unlimited times
 *
 * Usage:
 *   npm start                    # Start/resume capturing
 *   npm run status               # Show progress summary
 *   node capture.js --city brisbane   # Only capture one city
 *   node capture.js --resume     # Explicit resume (same as npm start)
 *   node capture.js --status     # Progress report
 *   node capture.js --recheck    # Re-capture listed properties (after phase)
 */

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

// --- Config ---
const ADDRESSES_FILE = path.join(__dirname, 'addresses.json');
const PROGRESS_FILE = path.join(__dirname, 'progress.json');
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const VIEWPORT = { width: 1440, height: 900 };

// Rate limiting: 4-5 seconds between requests
// 15,000 properties ÷ 4.5s avg = ~18.75 hours
const MIN_DELAY_MS = 3000;
const MAX_DELAY_MS = 6000;

// Browser settings
const NAVIGATION_TIMEOUT = 45000;
const PAGE_SETTLE_MS = 2500;

// How often to print progress (every N captures)
const PROGRESS_INTERVAL = 25;

// --- Progress tracking ---

function loadProgress() {
    if (fs.existsSync(PROGRESS_FILE)) {
        return JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf-8'));
    }
    return {
        started_at: new Date().toISOString(),
        last_updated: new Date().toISOString(),
        total: 0,
        completed: 0,
        failed: 0,
        skipped: 0,
        properties: {},  // slug -> { status, capturedAt, valuation, error }
    };
}

function saveProgress(progress) {
    progress.last_updated = new Date().toISOString();
    // Write to temp file then rename (atomic write — safe against crashes)
    const tmp = PROGRESS_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(progress, null, 2));
    fs.renameSync(tmp, PROGRESS_FILE);
}

// --- Address/URL helpers ---

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

// --- Valuation extraction ---

function extractValuationFromText(text) {
    const result = {
        estimateLow: null,
        estimateMid: null,
        estimateHigh: null,
        accuracy: null,
        updatedDate: null,
        isForSale: false,
        listingPrice: null,
        rentalEstimate: null,
    };

    const lowMatch = text.match(/LOW\s*\n?\s*\$?([\d,.]+[kmKM]?)/i);
    const midMatch = text.match(/MID\s*\n?\s*\$?([\d,.]+[kmKM]?)/i);
    const highMatch = text.match(/HIGH\s*\n?\s*\$?([\d,.]+[kmKM]?)/i);

    if (lowMatch) result.estimateLow = '$' + lowMatch[1];
    if (midMatch) result.estimateMid = '$' + midMatch[1];
    if (highMatch) result.estimateHigh = '$' + highMatch[1];

    const accMatch = text.match(/(?:rated\s+|accuracy[:\s]*)(high|medium|low)/i);
    if (accMatch) result.accuracy = accMatch[1].toLowerCase();

    const dateMatch = text.match(/Updated:\s*(\d{1,2}\s+\w+,?\s*\d{4})/i);
    if (dateMatch) result.updatedDate = dateMatch[1];

    result.isForSale = /currently\s+(?:for\s+sale|listed)/i.test(text);

    // Try to grab listing price if for sale
    if (result.isForSale) {
        // Look for price text in the banner area
        const priceMatch = text.match(/(?:for\s+sale|listed)\s*\n([^\n]+)/i);
        if (priceMatch) result.listingPrice = priceMatch[1].trim();
    }

    const rentalMatch = text.match(/PER\s+WEEK\s*\n?\s*\$?([\d,]+)/i);
    if (rentalMatch) result.rentalEstimate = '$' + rentalMatch[1] + '/week';

    return result;
}

// --- Core capture function ---

async function captureProperty(page, address, outputDir, label) {
    const url = addressToProfileUrl(address);

    await page.goto(url, { waitUntil: 'networkidle2', timeout: NAVIGATION_TIMEOUT });
    await new Promise(r => setTimeout(r, PAGE_SETTLE_MS));

    // Check if Domain returned a valid property profile (not a 404/error page)
    const pageTitle = await page.title();
    if (/page not found|404|error/i.test(pageTitle)) {
        return { success: false, error: 'Page not found (404)', url };
    }

    fs.mkdirSync(outputDir, { recursive: true });

    // Full page screenshot
    const fullPath = path.join(outputDir, `${label}-full.png`);
    await page.screenshot({ path: fullPath, fullPage: true });

    // Extract text and valuation
    const pageText = await page.evaluate(() => document.body.innerText);
    const valuation = extractValuationFromText(pageText);

    // Scroll to valuation section and take viewport screenshot
    await page.evaluate(() => {
        const headings = document.querySelectorAll('h2, h3, h4');
        for (const h of headings) {
            if (/property\s*value/i.test(h.textContent)) {
                h.scrollIntoView({ block: 'start', behavior: 'instant' });
                window.scrollBy(0, -80);
                return;
            }
        }
        const est = document.querySelector('[data-testid*="estimate"]');
        if (est) {
            est.scrollIntoView({ block: 'start', behavior: 'instant' });
            window.scrollBy(0, -80);
        }
    });
    await new Promise(r => setTimeout(r, 500));

    const valPath = path.join(outputDir, `${label}-valuation.png`);
    await page.screenshot({ path: valPath });

    // Save data JSON
    const captureData = {
        url,
        address,
        label,
        capturedAt: new Date().toISOString(),
        pageTitle,
        valuation,
        screenshots: {
            full: `${label}-full.png`,
            valuation: `${label}-valuation.png`,
        },
    };
    fs.writeFileSync(
        path.join(outputDir, `${label}-data.json`),
        JSON.stringify(captureData, null, 2)
    );

    return { success: true, valuation, url };
}

// --- Main capture loop ---

async function runCapture(cityFilter) {
    // Load addresses
    if (!fs.existsSync(ADDRESSES_FILE)) {
        console.error(`ERROR: ${ADDRESSES_FILE} not found.`);
        console.error('Run the address sampling script first, or pull from GitHub.');
        process.exit(1);
    }

    const addresses = JSON.parse(fs.readFileSync(ADDRESSES_FILE, 'utf-8'));
    const progress = loadProgress();

    // Filter by city if specified
    let workList = addresses;
    if (cityFilter) {
        workList = addresses.filter(a => a.city.toLowerCase() === cityFilter.toLowerCase());
        console.log(`Filtered to city: ${cityFilter} (${workList.length} properties)`);
    }

    progress.total = addresses.length;

    // Count what's already done
    const remaining = workList.filter(a => {
        const slug = addressToSlug(a.address);
        const entry = progress.properties[slug];
        return !entry || entry.status === 'failed';
    });

    console.log(`\n=== Domain Valuation Tracker ===`);
    console.log(`Total addresses: ${workList.length}`);
    console.log(`Already captured: ${workList.length - remaining.length}`);
    console.log(`Remaining: ${remaining.length}`);

    if (remaining.length === 0) {
        console.log('\nAll properties have been captured! Nothing to do.');
        console.log('Run with --recheck to re-capture properties that are now listed.');
        return;
    }

    const estimatedHours = (remaining.length * 4.5 / 3600).toFixed(1);
    console.log(`Estimated time: ~${estimatedHours} hours at ~4.5s per property`);
    console.log(`\nStarting in 3 seconds... (Ctrl+C to stop, progress is saved)\n`);
    await new Promise(r => setTimeout(r, 3000));

    // Launch browser
    let browser = await puppeteer.launch({
        headless: 'new',
        args: [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
        ],
    });

    let page = await browser.newPage();
    await page.setViewport(VIEWPORT);
    await page.setUserAgent(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    );

    let capturedThisSession = 0;
    const sessionStart = Date.now();

    // Graceful shutdown on Ctrl+C
    let stopping = false;
    process.on('SIGINT', () => {
        if (stopping) {
            console.log('\nForce quit.');
            process.exit(1);
        }
        stopping = true;
        console.log('\n\nStopping after current capture... (progress saved, run again to resume)');
    });

    for (const entry of remaining) {
        if (stopping) break;

        const slug = addressToSlug(entry.address);
        const outputDir = path.join(SCREENSHOTS_DIR, entry.city, slug);

        try {
            const result = await captureProperty(page, entry.address, outputDir, 'before');

            if (result.success) {
                progress.properties[slug] = {
                    status: 'captured',
                    capturedAt: new Date().toISOString(),
                    city: entry.city,
                    suburb: entry.suburb,
                    address: entry.address,
                    valuation: result.valuation,
                    isForSale: result.valuation.isForSale,
                };
                progress.completed++;
                capturedThisSession++;

                const emoji = result.valuation.isForSale ? '🔴' : '✓';
                const valText = result.valuation.estimateMid || 'no estimate';
                process.stdout.write(
                    `  ${emoji} [${progress.completed}/${progress.total}] ${entry.address} — ${valText}\n`
                );
            } else {
                progress.properties[slug] = {
                    status: 'no_profile',
                    capturedAt: new Date().toISOString(),
                    city: entry.city,
                    address: entry.address,
                    error: result.error,
                };
                progress.skipped++;
                process.stdout.write(
                    `  ⏭ [${progress.completed}/${progress.total}] ${entry.address} — ${result.error}\n`
                );
            }
        } catch (err) {
            progress.properties[slug] = {
                status: 'failed',
                city: entry.city,
                address: entry.address,
                error: err.message,
                failedAt: new Date().toISOString(),
            };
            progress.failed++;
            process.stdout.write(
                `  ✗ [${progress.completed}/${progress.total}] ${entry.address} — ERROR: ${err.message}\n`
            );

            // If browser crashed, relaunch
            if (err.message.includes('Target closed') || err.message.includes('Session closed') || err.message.includes('Protocol error')) {
                console.log('  Browser crashed, relaunching...');
                try { await browser.close(); } catch (e) {}
                browser = await puppeteer.launch({
                    headless: 'new',
                    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
                });
                page = await browser.newPage();
                await page.setViewport(VIEWPORT);
                await page.setUserAgent(
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                );
            }
        }

        // Save progress after EVERY capture (crash-safe)
        saveProgress(progress);

        // Progress summary every N captures
        if (capturedThisSession > 0 && capturedThisSession % PROGRESS_INTERVAL === 0) {
            const elapsed = (Date.now() - sessionStart) / 1000;
            const rate = capturedThisSession / elapsed;
            const remainingCount = remaining.length - capturedThisSession;
            const etaMinutes = Math.round(remainingCount / rate / 60);
            console.log(
                `\n  --- Progress: ${progress.completed}/${progress.total} done, ` +
                `${progress.failed} failed, ${progress.skipped} skipped, ` +
                `${rate.toFixed(1)}/sec, ETA ~${etaMinutes} min ---\n`
            );
        }

        // Random delay between requests
        if (!stopping) {
            const delay = MIN_DELAY_MS + Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS);
            await new Promise(r => setTimeout(r, delay));
        }
    }

    await browser.close();

    // Final summary
    const elapsed = ((Date.now() - sessionStart) / 1000 / 60).toFixed(1);
    console.log(`\n=== Session Complete ===`);
    console.log(`Captured this session: ${capturedThisSession}`);
    console.log(`Total completed: ${progress.completed}/${progress.total}`);
    console.log(`Failed: ${progress.failed}, Skipped: ${progress.skipped}`);
    console.log(`Session duration: ${elapsed} minutes`);
    console.log(`Progress saved to: ${PROGRESS_FILE}`);
}

// --- Recheck: capture "after" for properties that are now listed ---

async function runRecheck() {
    const progress = loadProgress();
    const captured = Object.values(progress.properties).filter(
        p => p.status === 'captured' && !p.isForSale && !p.rechecked
    );

    console.log(`\n=== Recheck Mode ===`);
    console.log(`Properties to recheck: ${captured.length}`);
    console.log(`(Looking for properties that have been listed since baseline capture)\n`);

    if (captured.length === 0) {
        console.log('No properties to recheck.');
        return;
    }

    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });

    const page = await browser.newPage();
    await page.setViewport(VIEWPORT);
    await page.setUserAgent(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    );

    let found = 0;
    let checked = 0;

    let stopping = false;
    process.on('SIGINT', () => {
        stopping = true;
        console.log('\nStopping...');
    });

    for (const entry of captured) {
        if (stopping) break;

        const slug = addressToSlug(entry.address);
        const outputDir = path.join(SCREENSHOTS_DIR, entry.city, slug);

        try {
            const result = await captureProperty(page, entry.address, outputDir, 'after');
            checked++;

            if (result.success && result.valuation.isForSale) {
                found++;
                const beforeMid = entry.valuation?.estimateMid || '?';
                const afterMid = result.valuation.estimateMid || '?';
                const changed = beforeMid !== afterMid;

                progress.properties[slug].rechecked = true;
                progress.properties[slug].recheckedAt = new Date().toISOString();
                progress.properties[slug].afterValuation = result.valuation;
                progress.properties[slug].valuationChanged = changed;
                progress.properties[slug].isNowForSale = true;

                const indicator = changed ? '⚠️  CHANGED' : 'unchanged';
                console.log(`  🔴 NOW LISTED: ${entry.address}`);
                console.log(`     Before: ${beforeMid} → After: ${afterMid} (${indicator})`);
            } else {
                progress.properties[slug].rechecked = true;
                progress.properties[slug].recheckedAt = new Date().toISOString();
                progress.properties[slug].isNowForSale = false;
            }
        } catch (err) {
            console.log(`  ✗ ${entry.address}: ${err.message}`);
        }

        saveProgress(progress);

        if (checked % 50 === 0) {
            console.log(`  --- Checked ${checked}/${captured.length}, found ${found} new listings ---`);
        }

        const delay = MIN_DELAY_MS + Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS);
        await new Promise(r => setTimeout(r, delay));
    }

    await browser.close();
    console.log(`\n=== Recheck Complete ===`);
    console.log(`Checked: ${checked}, New listings found: ${found}`);
}

// --- Status report ---

function showStatus() {
    if (!fs.existsSync(PROGRESS_FILE)) {
        console.log('No progress file found. Run `npm start` to begin capturing.');
        return;
    }

    const progress = JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf-8'));
    const props = Object.values(progress.properties);

    const byCityStatus = {};
    for (const p of props) {
        const city = p.city || 'unknown';
        if (!byCityStatus[city]) byCityStatus[city] = { captured: 0, failed: 0, skipped: 0, listed: 0, changed: 0 };
        if (p.status === 'captured') byCityStatus[city].captured++;
        if (p.status === 'failed') byCityStatus[city].failed++;
        if (p.status === 'no_profile') byCityStatus[city].skipped++;
        if (p.isForSale || p.isNowForSale) byCityStatus[city].listed++;
        if (p.valuationChanged) byCityStatus[city].changed++;
    }

    console.log(`\n=== Valuation Tracker Status ===`);
    console.log(`Started:  ${progress.started_at}`);
    console.log(`Updated:  ${progress.last_updated}`);
    console.log(`Total:    ${progress.total}`);
    console.log(`\nPer city:`);
    console.log(`  ${'City'.padEnd(15)} ${'Captured'.padStart(10)} ${'Failed'.padStart(10)} ${'Skipped'.padStart(10)} ${'Listed'.padStart(10)} ${'Changed'.padStart(10)}`);
    for (const [city, s] of Object.entries(byCityStatus).sort()) {
        console.log(
            `  ${city.padEnd(15)} ${String(s.captured).padStart(10)} ${String(s.failed).padStart(10)} ${String(s.skipped).padStart(10)} ${String(s.listed).padStart(10)} ${String(s.changed).padStart(10)}`
        );
    }

    const totalCaptured = props.filter(p => p.status === 'captured').length;
    const pct = progress.total > 0 ? ((totalCaptured / progress.total) * 100).toFixed(1) : 0;
    console.log(`\nOverall: ${totalCaptured}/${progress.total} (${pct}%)`);

    if (progress.total > totalCaptured) {
        const remaining = progress.total - totalCaptured;
        const hours = (remaining * 4.5 / 3600).toFixed(1);
        console.log(`Remaining: ${remaining} (~${hours} hours)`);
    }
}

// --- CLI ---

async function main() {
    const args = process.argv.slice(2);

    if (args.includes('--status')) {
        showStatus();
        return;
    }

    if (args.includes('--recheck')) {
        await runRecheck();
        return;
    }

    // City filter
    const cityIdx = args.indexOf('--city');
    const cityFilter = cityIdx >= 0 ? args[cityIdx + 1] : null;

    await runCapture(cityFilter);
}

main().catch(err => {
    console.error('Fatal error:', err.message);
    process.exit(1);
});
