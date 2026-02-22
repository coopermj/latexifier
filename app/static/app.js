// ─── State ────────────────────────────────────────────────────────────────────
let coverImageBase64 = null;
let bulletinPdfBase64 = null;
let prayerPdfBase64 = null;
let extractedOutline = null;    // SermonOutline dict from /web/extract
let extractedCandidates = null; // {source_key: {source_name, entries[]}} from /web/extract

// ─── Wizard Navigation ────────────────────────────────────────────────────────
function showStep(n) {
    [1, 2, 3].forEach(i => {
        document.getElementById(`step-${i}`).classList.toggle('hidden', i !== n);
        const ind = document.getElementById(`step-ind-${i}`);
        ind.classList.toggle('active', i === n);
        ind.classList.toggle('done', i < n);
    });
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
const passwordModal = document.getElementById('password-modal');
const mainContent   = document.getElementById('main-content');

async function checkAuth() {
    try {
        const resp = await fetch('/web/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: '' }),
            credentials: 'include',
        });
        if (resp.status !== 401) { showMainContent(); return; }
    } catch (e) {}
    showPasswordModal();
}

function showPasswordModal() {
    passwordModal.classList.remove('hidden');
    mainContent.classList.add('hidden');
    document.getElementById('password-input').focus();
}

function showMainContent() {
    passwordModal.classList.add('hidden');
    mainContent.classList.remove('hidden');
    showStep(1);
}

document.getElementById('password-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = document.getElementById('password-error');
    err.classList.add('hidden');
    try {
        const resp = await fetch('/web/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: document.getElementById('password-input').value }),
            credentials: 'include',
        });
        const data = await resp.json();
        if (data.valid) { showMainContent(); document.getElementById('password-input').value = ''; }
        else { err.classList.remove('hidden'); document.getElementById('password-input').select(); }
    } catch (_) {
        err.textContent = 'Connection error. Please try again.';
        err.classList.remove('hidden');
    }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
    try { await fetch('/web/logout', { method: 'POST', credentials: 'include' }); } catch (_) {}
    coverImageBase64 = bulletinPdfBase64 = prayerPdfBase64 = null;
    extractedOutline = extractedCandidates = null;
    document.getElementById('notes').value = '';
    clearImagePreview();
    clearBulletinPdf();
    clearPrayerPdf();
    document.getElementById('extract-error').classList.add('hidden');
    showPasswordModal();
});

// ─── File helpers ──────────────────────────────────────────────────────────────
function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload  = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// Cover image
document.getElementById('cover-wrapper').addEventListener('click', () =>
    document.getElementById('cover-image').click());

document.getElementById('cover-image').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) { clearImagePreview(); return; }
    document.getElementById('file-name').textContent = file.name;
    try {
        coverImageBase64 = await readFileAsBase64(file);
        document.getElementById('preview-img').src = URL.createObjectURL(file);
        document.getElementById('image-preview').classList.remove('hidden');
    } catch (_) { clearImagePreview(); }
});

document.getElementById('clear-image').addEventListener('click', clearImagePreview);

function clearImagePreview() {
    document.getElementById('cover-image').value = '';
    document.getElementById('file-name').textContent = 'No file chosen';
    document.getElementById('image-preview').classList.add('hidden');
    document.getElementById('preview-img').src = '';
    coverImageBase64 = null;
}

// Bulletin PDF
document.getElementById('bulletin-wrapper').addEventListener('click', () =>
    document.getElementById('bulletin-pdf').click());

document.getElementById('bulletin-pdf').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) { clearBulletinPdf(); return; }
    document.getElementById('bulletin-file-name').textContent = file.name;
    try {
        bulletinPdfBase64 = await readFileAsBase64(file);
        document.getElementById('clear-bulletin').classList.remove('hidden');
    } catch (_) { clearBulletinPdf(); }
});

document.getElementById('clear-bulletin').addEventListener('click', clearBulletinPdf);

function clearBulletinPdf() {
    document.getElementById('bulletin-pdf').value = '';
    document.getElementById('bulletin-file-name').textContent = 'No file chosen';
    bulletinPdfBase64 = null;
    document.getElementById('clear-bulletin').classList.add('hidden');
}

// Prayer PDF
document.getElementById('prayer-wrapper').addEventListener('click', () =>
    document.getElementById('prayer-pdf').click());

document.getElementById('prayer-pdf').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) { clearPrayerPdf(); return; }
    document.getElementById('prayer-file-name').textContent = file.name;
    try {
        prayerPdfBase64 = await readFileAsBase64(file);
        document.getElementById('clear-prayer').classList.remove('hidden');
    } catch (_) { clearPrayerPdf(); }
});

document.getElementById('clear-prayer').addEventListener('click', clearPrayerPdf);

function clearPrayerPdf() {
    document.getElementById('prayer-pdf').value = '';
    document.getElementById('prayer-file-name').textContent = 'No file chosen';
    prayerPdfBase64 = null;
    document.getElementById('clear-prayer').classList.add('hidden');
}

// ─── Step 1: Extract ──────────────────────────────────────────────────────────
document.getElementById('sermon-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('extract-error').classList.add('hidden');

    const notes = document.getElementById('notes').value.trim();
    if (!notes) { showExtractError('Please enter sermon notes'); return; }

    const commentaries = ['commentary-mhc', 'commentary-calvin', 'commentary-scofield']
        .map(id => document.getElementById(id))
        .filter(el => el && el.checked)
        .map(el => el.value);

    setExtracting(true);

    try {
        const resp = await fetch('/web/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes, image: coverImageBase64, commentaries }),
            credentials: 'include',
        });

        if (resp.status === 401) { showPasswordModal(); return; }

        const data = await resp.json();

        if (!data.success) { showExtractError(data.error || 'Extraction failed'); return; }

        extractedOutline    = data.outline;
        extractedCandidates = data.candidates;

        renderReviewStep(data.outline, data.candidates);
        showStep(2);

    } catch (_) {
        showExtractError('Connection error. Please try again.');
    } finally {
        setExtracting(false);
    }
});

function setExtracting(loading) {
    document.getElementById('extract-btn').disabled = loading;
    document.getElementById('extract-btn-text').textContent = loading ? 'Extracting…' : 'Extract Outline';
    document.getElementById('extract-btn-spinner').classList.toggle('hidden', !loading);
}

function showExtractError(msg) {
    document.getElementById('extract-error-message').textContent = msg;
    document.getElementById('extract-error').classList.remove('hidden');
}

// ─── Step 2: Review ───────────────────────────────────────────────────────────
function renderReviewStep(outline, candidates) {
    // Outline summary
    const meta = outline.metadata;
    const summaryEl = document.getElementById('outline-summary');
    summaryEl.innerHTML = `
        <h2 class="outline-title">${escapeHtml(meta.title)}</h2>
        <p class="outline-meta">${[meta.speaker, meta.date].filter(Boolean).map(escapeHtml).join(' · ')}</p>
        <p class="outline-passage">Main passage: <strong>${escapeHtml(outline.main_passage)}</strong></p>
    `;

    // Commentary cards
    const cardsEl = document.getElementById('commentary-cards');
    cardsEl.innerHTML = '';

    const sourceKeys = Object.keys(candidates || {});

    if (sourceKeys.length === 0) {
        cardsEl.innerHTML = '<p class="no-commentary">No commentary selected or no results found.</p>';
        return;
    }

    sourceKeys.forEach(sourceKey => {
        const sourceData = candidates[sourceKey];
        const card = document.createElement('div');
        card.className = 'commentary-card';

        let entriesHtml = sourceData.entries.map((entry, i) => {
            const verseLabel = entry.verse_end && entry.verse_end !== entry.verse_start
                ? `vv.${entry.verse_start}–${entry.verse_end}`
                : `v.${entry.verse_start}`;
            const checkId = `entry-${sourceKey}-${i}`;
            const shortText = entry.text.length > 150
                ? entry.text.slice(0, 150) + '…'
                : entry.text;
            const needsExpand = entry.text.length > 150;

            return `
                <label class="commentary-entry">
                    <input type="checkbox" id="${checkId}" data-source-key="${sourceKey}" data-entry-index="${i}" checked>
                    <span class="entry-verse">${escapeHtml(verseLabel)}</span>
                    <span class="entry-text" data-full="${escapeHtml(entry.text)}" data-short="${escapeHtml(shortText)}">
                        ${escapeHtml(shortText)}
                    </span>
                    ${needsExpand ? `<button type="button" class="show-more-btn" data-expanded="false">show more ▾</button>` : ''}
                </label>
            `;
        }).join('');

        card.innerHTML = `
            <div class="card-source-name">${escapeHtml(sourceData.source_name)}</div>
            <div class="card-entries">${entriesHtml}</div>
        `;
        cardsEl.appendChild(card);
    });

    // Wire up show more/less toggles
    cardsEl.querySelectorAll('.show-more-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const expanded = btn.dataset.expanded === 'true';
            const textEl = btn.previousElementSibling;
            textEl.textContent = expanded ? textEl.dataset.short : textEl.dataset.full;
            btn.textContent = expanded ? 'show more ▾' : 'show less ▴';
            btn.dataset.expanded = String(!expanded);
        });
    });
}

// Back to step 1
document.getElementById('back-btn').addEventListener('click', () => {
    document.getElementById('review-error').classList.add('hidden');
    showStep(1);
});

// ─── Step 2 → 3: Generate ─────────────────────────────────────────────────────
document.getElementById('generate-btn').addEventListener('click', async () => {
    document.getElementById('review-error').classList.add('hidden');

    // Collect selected entries grouped by source_name
    const overrideMap = {}; // source_name → {source_name, entries[]}
    const cardsEl = document.getElementById('commentary-cards');

    cardsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        if (!cb.checked) return;
        const sourceKey = cb.dataset.sourceKey;
        const idx = parseInt(cb.dataset.entryIndex, 10);
        const sourceData = extractedCandidates[sourceKey];
        const entry = sourceData.entries[idx];
        const name = sourceData.source_name;
        if (!overrideMap[name]) overrideMap[name] = { source_name: name, entries: [] };
        overrideMap[name].entries.push({
            verse_start: entry.verse_start,
            verse_end: entry.verse_end,
            text: entry.text,
        });
    });

    const commentaryOverrides = Object.values(overrideMap);

    setGenerating(true);

    try {
        const body = {
            notes: document.getElementById('notes').value,
            image: coverImageBase64,
            bulletin_pdf: bulletinPdfBase64,
            prayer_pdf: prayerPdfBase64,
            outline: extractedOutline,
            commentary_overrides: commentaryOverrides,
        };

        const resp = await fetch('/web/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            credentials: 'include',
        });

        if (resp.status === 401) { showPasswordModal(); return; }

        const data = await resp.json();

        if (data.success && data.url) {
            document.getElementById('download-link').href = data.url;
            const texLink = document.getElementById('download-tex-link');
            if (data.tex_url) { texLink.href = data.tex_url; texLink.style.display = 'inline-block'; }
            else { texLink.style.display = 'none'; }
            showStep(3);
        } else {
            document.getElementById('review-error-message').textContent = data.error || 'Unknown error';
            document.getElementById('review-error').classList.remove('hidden');
        }
    } catch (_) {
        document.getElementById('review-error-message').textContent = 'Connection error. Please try again.';
        document.getElementById('review-error').classList.remove('hidden');
    } finally {
        setGenerating(false);
    }
});

function setGenerating(loading) {
    document.getElementById('generate-btn').disabled = loading;
    document.getElementById('generate-btn-text').textContent = loading ? 'Generating…' : 'Generate PDF';
    document.getElementById('generate-btn-spinner').classList.toggle('hidden', !loading);
}

// ─── Step 3: Done ─────────────────────────────────────────────────────────────
document.getElementById('start-over-btn').addEventListener('click', () => {
    extractedOutline = extractedCandidates = null;
    document.getElementById('notes').value = '';
    clearImagePreview(); clearBulletinPdf(); clearPrayerPdf();
    ['commentary-mhc', 'commentary-calvin', 'commentary-scofield'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.checked = false;
    });
    showStep(1);
});

// ─── Utilities ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─── Init ─────────────────────────────────────────────────────────────────────
checkAuth();
