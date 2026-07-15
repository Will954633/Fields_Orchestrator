#!/usr/bin/env node
/**
 * Export comparison data for the propertybullshit.com website.
 *
 * Reads progress.json, finds properties where the valuation changed
 * between baseline and recheck, and outputs website-ready JSON.
 */

const fs = require('fs');
const path = require('path');

const PROGRESS_FILE = path.join(__dirname, 'progress.json');
const EXPORT_DIR = path.join(__dirname, 'export');

function main() {
    if (!fs.existsSync(PROGRESS_FILE)) {
        console.error('No progress.json found. Run captures first.');
        process.exit(1);
    }

    const progress = JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf-8'));
    const props = Object.entries(progress.properties);

    // Find properties where we have before + after data
    const comparisons = [];
    const monitored = [];

    for (const [slug, p] of props) {
        if (p.status !== 'captured') continue;

        if (p.isNowForSale && p.afterValuation) {
            comparisons.push({
                address: p.address,
                suburb: p.suburb,
                city: p.city,
                slug,
                listing_url: null,
                listing_price: p.afterValuation.listingPrice,
                valuation_changed: p.valuationChanged || false,
                before: {
                    date: p.capturedAt,
                    low: p.valuation?.estimateLow,
                    mid: p.valuation?.estimateMid,
                    high: p.valuation?.estimateHigh,
                    accuracy: p.valuation?.accuracy,
                    screenshot: `screenshots/${p.city}/${slug}/before-valuation.png`,
                },
                after: {
                    date: p.recheckedAt,
                    low: p.afterValuation?.estimateLow,
                    mid: p.afterValuation?.estimateMid,
                    high: p.afterValuation?.estimateHigh,
                    accuracy: p.afterValuation?.accuracy,
                    screenshot: `screenshots/${p.city}/${slug}/after-valuation.png`,
                },
            });
        } else if (!p.isForSale) {
            monitored.push({
                address: p.address,
                suburb: p.suburb,
                city: p.city,
                status: 'monitoring',
                baseline_valuation: p.valuation?.estimateMid,
                baseline_date: p.capturedAt,
            });
        }
    }

    // Sort comparisons: changed first, then by date
    comparisons.sort((a, b) => {
        if (a.valuation_changed !== b.valuation_changed) return b.valuation_changed ? 1 : -1;
        return new Date(b.after.date) - new Date(a.after.date);
    });

    const exportData = {
        generated_at: new Date().toISOString(),
        total_tracked: props.filter(([, p]) => p.status === 'captured').length,
        total_with_changes: comparisons.filter(c => c.valuation_changed).length,
        comparisons,
        monitored: monitored.slice(0, 100), // Cap at 100 for website
    };

    fs.mkdirSync(EXPORT_DIR, { recursive: true });
    const outPath = path.join(EXPORT_DIR, 'comparisons.json');
    fs.writeFileSync(outPath, JSON.stringify(exportData, null, 2));

    console.log(`\n=== Export Complete ===`);
    console.log(`Comparisons (before + after): ${comparisons.length}`);
    console.log(`  With valuation change: ${exportData.total_with_changes}`);
    console.log(`Monitored (baseline only): ${monitored.length}`);
    console.log(`Output: ${outPath}`);
}

main();
