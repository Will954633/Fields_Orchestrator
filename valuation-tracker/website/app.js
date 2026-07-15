/**
 * PropertyBullshit.com — Frontend Application
 *
 * Loads comparison data and renders the evidence table.
 * Screenshots are served from /screenshots/ directory.
 */

const DATA_URL = './data/comparisons.json';
const SCREENSHOT_BASE = './screenshots/';

let comparisonData = null;

async function loadData() {
    try {
        const resp = await fetch(DATA_URL);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        comparisonData = await resp.json();
        renderStats(comparisonData);
        renderComparisons(comparisonData.comparisons);
        renderMonitored(comparisonData.monitored);
    } catch (err) {
        console.error('Failed to load comparison data:', err);
        // Show demo data for development/preview
        showDemoData();
    }
}

function renderStats(data) {
    document.getElementById('total-tracked').textContent = data.total_tracked || 0;
    document.getElementById('total-listed').textContent = data.comparisons?.length || 0;
    document.getElementById('total-changed').textContent = data.total_with_changes || 0;
}

function renderComparisons(comparisons) {
    const tbody = document.getElementById('comparison-body');
    const noData = document.getElementById('no-data');

    if (!comparisons || comparisons.length === 0) {
        document.querySelector('.table-wrap').style.display = 'none';
        noData.style.display = 'block';
        return;
    }

    tbody.innerHTML = '';

    for (const c of comparisons) {
        const tr = document.createElement('tr');
        tr.onclick = () => showModal(c);

        const changed = c.valuation_changed;
        const changeBadge = changed
            ? '<span class="change-badge changed">CHANGED</span>'
            : '<span class="change-badge unchanged">Unchanged</span>';

        tr.innerHTML = `
            <td><strong>${escapeHtml(c.address)}</strong></td>
            <td>${escapeHtml(capitalise(c.suburb))}</td>
            <td>${c.before?.mid || '—'}</td>
            <td>${c.after?.mid || '—'}</td>
            <td>${changeBadge}</td>
            <td><button class="evidence-btn" onclick="event.stopPropagation(); showModal(${JSON.stringify(c).replace(/"/g, '&quot;')})">View Evidence</button></td>
        `;

        tbody.appendChild(tr);
    }
}

function renderMonitored(monitored) {
    const grid = document.getElementById('monitored-list');
    const section = document.getElementById('monitored-section');

    if (!monitored || monitored.length === 0) {
        section.style.display = 'none';
        return;
    }

    // Only show non-listed properties
    const watching = monitored.filter(m => m.status === 'monitoring');
    if (watching.length === 0) {
        section.style.display = 'none';
        return;
    }

    grid.innerHTML = '';

    for (const m of watching.slice(0, 50)) { // Show max 50
        const card = document.createElement('div');
        card.className = 'monitored-card';
        card.innerHTML = `
            <div class="address">
                <span class="monitored-status"></span>
                ${escapeHtml(m.address)}
            </div>
            <div class="meta">
                ${capitalise(m.suburb)} &bull;
                Baseline: ${m.baseline_valuation || '—'} &bull;
                ${m.baseline_date ? formatDate(m.baseline_date) : ''}
            </div>
        `;
        grid.appendChild(card);
    }
}

function showModal(comparison) {
    const modal = document.getElementById('screenshot-modal');
    document.getElementById('modal-title').textContent = comparison.address;
    document.getElementById('modal-before-date').textContent =
        `Captured: ${comparison.before?.date ? formatDate(comparison.before.date) : 'N/A'}`;
    document.getElementById('modal-after-date').textContent =
        `Captured: ${comparison.after?.date ? formatDate(comparison.after.date) : 'N/A'}`;

    const beforeImg = document.getElementById('modal-before-img');
    const afterImg = document.getElementById('modal-after-img');

    beforeImg.src = comparison.before?.screenshot
        ? SCREENSHOT_BASE + comparison.before.screenshot
        : '';
    afterImg.src = comparison.after?.screenshot
        ? SCREENSHOT_BASE + comparison.after.screenshot
        : '';

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('screenshot-modal').classList.remove('active');
    document.body.style.overflow = '';
}

function showDemoData() {
    // Demo data for preview before real data is collected
    const demo = {
        total_tracked: 3,
        total_with_changes: 2,
        comparisons: [
            {
                address: '28 Federal Place, Robina, QLD 4226',
                suburb: 'robina',
                slug: '28-federal-place-robina-qld-4226',
                listing_price: 'Expressions of Interest',
                valuation_changed: true,
                before: {
                    date: '2026-03-01T10:00:00+10:00',
                    low: '$1.45M', mid: '$1.65M', high: '$1.85M',
                    accuracy: 'high',
                    screenshot: '28-federal-place-robina-qld-4226/before-valuation.png',
                },
                after: {
                    date: '2026-03-15T14:00:00+10:00',
                    low: '$1.72M', mid: '$2M', high: '$2.28M',
                    accuracy: 'high',
                    screenshot: '28-federal-place-robina-qld-4226/after-valuation.png',
                },
            },
            {
                address: '18 Anglesea Court, Robina, QLD 4226',
                suburb: 'robina',
                slug: '18-anglesea-court-robina-qld-4226',
                listing_price: '$1,750,000',
                valuation_changed: true,
                before: {
                    date: '2026-03-01T10:00:00+10:00',
                    low: '$1.3M', mid: '$1.5M', high: '$1.7M',
                    accuracy: 'high',
                    screenshot: '18-anglesea-court-robina-qld-4226/before-valuation.png',
                },
                after: {
                    date: '2026-03-10T10:00:00+10:00',
                    low: '$1.55M', mid: '$1.8M', high: '$2.05M',
                    accuracy: 'high',
                    screenshot: '18-anglesea-court-robina-qld-4226/after-valuation.png',
                },
            },
        ],
        monitored: [
            { address: '42 Example Street, Robina, QLD 4226', suburb: 'robina', status: 'monitoring', baseline_valuation: '$850K', baseline_date: '2026-03-14T08:00:00+10:00' },
            { address: '15 Sample Ave, Varsity Lakes, QLD 4227', suburb: 'varsity_lakes', status: 'monitoring', baseline_valuation: '$1.2M', baseline_date: '2026-03-14T08:00:00+10:00' },
        ],
    };

    renderStats(demo);
    renderComparisons(demo.comparisons);
    renderMonitored(demo.monitored);
}

// --- Utilities ---

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

function capitalise(str) {
    if (!str) return '';
    return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatDate(isoStr) {
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return isoStr;
    }
}

// --- Event Listeners ---

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('screenshot-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// --- Init ---
loadData();
