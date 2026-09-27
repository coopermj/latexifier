// ─── State ────────────────────────────────────────────────────────────────────
let coverImageBase64 = null;
let bulletinPdfBase64 = null;
let notesPdfBase64 = null;
let notesPdfReading = false;
let prayerPdfBase64 = null;
let extractedOutline = null;    // SermonOutline dict from /web/extract
let extractedCandidates = null; // {source_key: {source_name, entries[]}} from /web/extract
let pdfBlobUrl = null;          // stored server URL for opening PDF in a new tab
let slidesPdfBase64 = null;
let slideAnalysis = null;
let slidesReading = false;
let slideReadVersion = 0;
let extractionVersion = 0;

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
    clearSlidesPdf();
    clearNotesPdf();
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

// Sermon notes PDF: an alternative to pasting notes. Read during extraction only.
document.getElementById('notes-pdf-wrapper').addEventListener('click', (event) => {
    if (event.target.id !== 'notes-pdf') document.getElementById('notes-pdf').click();
});
document.getElementById('notes-pdf').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    notesPdfBase64 = null;
    if (!file) { clearNotesPdf(); return; }
    if (file.size > 10 * 1024 * 1024 || !file.name.toLowerCase().endsWith('.pdf')) {
        clearNotesPdf();
        showExtractError('Choose a PDF no larger than 10 MB for sermon notes.');
        return;
    }
    notesPdfReading = true;
    document.getElementById('notes-pdf-file-name').textContent = `Reading ${file.name}…`;
    document.getElementById('clear-notes-pdf').classList.remove('hidden');
    try {
        notesPdfBase64 = await readFileAsBase64(file);
        document.getElementById('notes-pdf-file-name').textContent = file.name;
    } catch (_) {
        clearNotesPdf();
        showExtractError('The notes PDF could not be read. Choose it again.');
    } finally {
        notesPdfReading = false;
    }
});
document.getElementById('clear-notes-pdf').addEventListener('click', clearNotesPdf);
function clearNotesPdf() {
    notesPdfBase64 = null;
    notesPdfReading = false;
    document.getElementById('notes-pdf').value = '';
    document.getElementById('notes-pdf-file-name').textContent = 'No file chosen';
    document.getElementById('clear-notes-pdf').classList.add('hidden');
}

// Sermon slides are analyzed during extraction and reviewed before generation.
document.getElementById('slides-wrapper').addEventListener('click', (event) => {
    if (event.target.id !== 'slides-pdf') document.getElementById('slides-pdf').click();
});
document.getElementById('slides-pdf').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    const version = ++slideReadVersion;
    slidesPdfBase64 = slideAnalysis = null;
    document.getElementById('slide-review').innerHTML = '';
    if (!file) { clearSlidesPdf(); return; }
    if (file.size > 10 * 1024 * 1024 || !file.name.toLowerCase().endsWith('.pdf')) {
        clearSlidesPdf();
        showExtractError('Choose a PDF no larger than 10 MB for sermon slides.');
        return;
    }
    slidesReading = true;
    document.getElementById('slides-file-name').textContent = `Reading ${file.name}…`;
    document.getElementById('clear-slides').classList.remove('hidden');
    try {
        const content = await readFileAsBase64(file);
        if (version !== slideReadVersion) return;
        slidesPdfBase64 = content;
        document.getElementById('slides-file-name').textContent = file.name;
    } catch (_) {
        if (version !== slideReadVersion) return;
        clearSlidesPdf();
        showExtractError('The slides could not be read. Choose the PDF again.');
    } finally {
        if (version === slideReadVersion) slidesReading = false;
    }
});
document.getElementById('clear-slides').addEventListener('click', clearSlidesPdf);
function clearSlidesPdf() {
    slideReadVersion++;
    extractionVersion++;
    slidesPdfBase64 = slideAnalysis = null;
    slidesReading = false;
    document.getElementById('slides-pdf').value = '';
    document.getElementById('slides-file-name').textContent = 'No file chosen';
    document.getElementById('clear-slides').classList.add('hidden');
    document.getElementById('slide-review').innerHTML = '';
    document.getElementById('slide-review').classList.add('hidden');
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

// ─── Select all commentaries ──────────────────────────────────────────────────
document.getElementById('select-all-commentaries').addEventListener('click', () => {
    const checkboxes = document.querySelectorAll('#sermon-form .checkbox-group input[type="checkbox"]');
    const allChecked = [...checkboxes].every(cb => cb.checked);
    checkboxes.forEach(cb => { cb.checked = !allChecked; });
    document.getElementById('select-all-commentaries').textContent = allChecked ? 'Select all' : 'Deselect all';
});

document.querySelectorAll('#sermon-form .checkbox-group input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => {
        const checkboxes = document.querySelectorAll('#sermon-form .checkbox-group input[type="checkbox"]');
        const allChecked = [...checkboxes].every(c => c.checked);
        document.getElementById('select-all-commentaries').textContent = allChecked ? 'Deselect all' : 'Select all';
    });
});

// ─── Step 1: Extract ──────────────────────────────────────────────────────────
document.getElementById('sermon-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('extract-error').classList.add('hidden');

    const notes = document.getElementById('notes').value.trim();
    if (notesPdfReading) { showExtractError('The notes PDF is still being read. Please wait a moment.'); return; }
    if (!notes && !notesPdfBase64) { showExtractError('Please paste sermon notes or upload a notes PDF'); return; }
    if (slidesReading) { showExtractError('The slide PDF is still being read. Please wait a moment.'); return; }
    const requestVersion = ++extractionVersion;
    slideAnalysis = null;

    const commentaries = Array.from(
        document.querySelectorAll('#sermon-form input[type="checkbox"][id^="commentary-"]:checked')
    ).map(el => el.value);

    setExtracting(true);

    try {
        const resp = await fetch('/web/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes, notes_pdf: notesPdfBase64, image: coverImageBase64, commentaries, slides_pdf: slidesPdfBase64 }),
            credentials: 'include',
        });

        if (resp.status === 401) { showPasswordModal(); return; }

        const data = await resp.json();
        if (requestVersion !== extractionVersion) return;

        if (!data.success) { showExtractError(data.error || 'Extraction failed'); return; }

        extractedOutline    = data.outline;
        extractedCandidates = data.candidates;
        slideAnalysis = data.slide_analysis || null;

        renderReviewStep(data.outline, data.candidates);
        renderSlideReview(data.outline, data.slide_previews || {});
        showStep(2);

    } catch (_) {
        showExtractError('Connection error. Please try again.');
    } finally {
        setExtracting(false);
    }
});

function setExtracting(loading) {
    document.getElementById('extract-btn').disabled = loading;
    document.getElementById('extract-btn-text').textContent = loading ? (slidesPdfBase64 ? 'Reading outline and slides…' : notesPdfBase64 ? 'Reading notes PDF…' : 'Extracting…') : 'Extract Outline';
    document.getElementById('extract-btn-spinner').classList.toggle('hidden', !loading);
    document.querySelectorAll('#sermon-form input, #sermon-form textarea, #sermon-form button').forEach(el => { el.disabled = loading; });
}

function slideTargets(outline) {
    const targets = [];
    if (outline.foundational_principle) targets.push(['foundation', 'Main idea']);
    (outline.points || []).forEach((point, pi) => {
        if (point.sub_points?.length) {
            point.sub_points.forEach((sub, si) => targets.push([`p${pi}.s${si}`, `${point.title || `Point ${pi + 1}`} — ${sub.label || si + 1}. ${sub.title || sub.content || 'Subpoint'}`]));
        } else targets.push([`p${pi}`, point.title || `Point ${pi + 1}`]);
    });
    return targets;
}

function renderSlideReview(outline, previews) {
    const panel = document.getElementById('slide-review');
    panel.innerHTML = '';
    panel.classList.toggle('hidden', !slideAnalysis);
    if (!slideAnalysis) return;
    const targets = slideTargets(outline);
    const cards = slideAnalysis.items.map((item, index) => {
        const options = targets.map(([key, label]) => `<option value="${escapeHtml(key)}" ${key === item.target ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
        const preview = previews[`slide-${item.id}.png`];
        return `<article class="slide-addition">
            <label class="slide-toggle"><input type="checkbox" data-slide-index="${index}" ${item.enabled ? 'checked' : ''}>
                <span><strong>${escapeHtml(item.reference || item.label)}</strong><small>Slide ${item.slide} · ${item.kind === 'scripture' ? 'Scripture pullout' : item.kind === 'table' ? 'Table' : 'Image'}</small></span>
            </label>
            ${preview ? `<img class="slide-preview" src="data:image/png;base64,${escapeHtml(preview)}" alt="${escapeHtml(item.label)}">` : ''}
            <label class="slide-destination">Place with <select data-slide-target="${index}">${options}</select></label>
        </article>`;
    }).join('');
    const unmatched = slideAnalysis.unmatched_slides || [];
    panel.innerHTML = `<h3>Slide additions</h3><p class="slide-help">${slideAnalysis.page_count} slides reviewed. Choose additions and their matching outline sections. Repeated notes, main-passage verses and decorative artwork are skipped.</p>
        ${cards || '<p>No additional passages, images or tables were matched.</p>'}
        ${unmatched.length ? `<p class="slide-unmatched">Could not confidently match slides ${unmatched.join(', ')}. These slides will not be added.</p>` : ''}`;
}

function collectSlideAnalysis() {
    if (!slideAnalysis) return null;
    const reviewed = JSON.parse(JSON.stringify(slideAnalysis));
    document.querySelectorAll('[data-slide-index]').forEach(el => { reviewed.items[Number(el.dataset.slideIndex)].enabled = el.checked; });
    document.querySelectorAll('[data-slide-target]').forEach(el => { reviewed.items[Number(el.dataset.slideTarget)].target = el.value; });
    return reviewed;
}

function showExtractError(msg) {
    document.getElementById('extract-error-message').textContent = msg;
    document.getElementById('extract-error').classList.remove('hidden');
}

// ─── Step 2: Review ───────────────────────────────────────────────────────────
function tableNote(tables) {
    if (!tables || tables.length === 0) return '';
    return tables.map(t => {
        const cols = (t.headers || []).join(' / ');
        const name = t.caption || cols || 'Table';
        const rows = (t.rows || []).length;
        return `<p class="slide-help">Table: ${escapeHtml(name)} (${rows} row${rows === 1 ? '' : 's'})</p>`;
    }).join('');
}

function renderReviewStep(outline, candidates) {
    const meta = outline.metadata;
    const summaryEl = document.getElementById('outline-summary');

    let pointsHtml = '';
    if (outline.points && outline.points.length > 0) {
        pointsHtml = '<ol class="outline-points">' + outline.points.map((pt, pi) => {
            let subHtml = '';
            if (pt.sub_points && pt.sub_points.length > 0) {
                subHtml = '<ol class="outline-subpoints">' + pt.sub_points.map((sub, si) => {
                    const label = sub.label ? `<span class="sub-label">${escapeHtml(sub.label)}.</span> ` : '';
                    const text = sub.title || sub.content || '';
                    const verseVal = sub.scripture_verse || '';
                    const verseClass = verseVal ? 'verse-tag editable' : 'verse-tag editable verse-tag-empty';
                    return `<li>
                        ${label}<span contenteditable="true" class="editable sub-text"
                            data-edit-point="${pi}" data-edit-sub="${si}" data-edit-field="title"
                        >${escapeHtml(text)}</span>
                        <span contenteditable="true" class="${verseClass}"
                            data-edit-point="${pi}" data-edit-sub="${si}" data-edit-field="scripture_verse"
                            data-placeholder="+ verse"
                        >${escapeHtml(verseVal)}</span>
                    </li>`;
                }).join('') + '</ol>';
            }
            const ptRef = (pt.scripture_refs && pt.scripture_refs.length > 0) ? pt.scripture_refs[0] : '';
            const ptVerseClass = ptRef ? 'verse-tag editable' : 'verse-tag editable verse-tag-empty';
            return `<li>
                <strong contenteditable="true" class="editable point-title"
                    data-edit-point="${pi}" data-edit-field="title"
                >${escapeHtml(pt.title || '')}</strong>
                <span contenteditable="true" class="${ptVerseClass}"
                    data-edit-point="${pi}" data-edit-field="scripture_refs"
                    data-placeholder="+ verse"
                >${escapeHtml(ptRef)}</span>
                ${subHtml}
                ${tableNote(pt.tables)}
            </li>`;
        }).join('') + '</ol>';
    }
    pointsHtml += tableNote(outline.tables);

    summaryEl.innerHTML = `
        <div class="edit-meta-grid">
            <label class="edit-meta-label">Title
                <input id="edit-title" type="text" class="edit-input" value="${escapeHtml(meta.title || '')}">
            </label>
            <label class="edit-meta-label">Passage
                <input id="edit-passage" type="text" class="edit-input" value="${escapeHtml(outline.main_passage || '')}">
            </label>
            <label class="edit-meta-label">Speaker
                <input id="edit-speaker" type="text" class="edit-input" value="${escapeHtml(meta.speaker || '')}">
            </label>
            <label class="edit-meta-label">Date
                <input id="edit-date" type="text" class="edit-input" value="${escapeHtml(meta.date || '')}">
            </label>
        </div>
        ${pointsHtml}
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
            outline: collectEditedOutline(),
            commentary_overrides: commentaryOverrides,
            slides_pdf: slidesPdfBase64,
            slide_analysis: collectSlideAnalysis(),
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
            const texLink = document.getElementById('download-tex-link');
            if (data.tex_url) { texLink.href = data.tex_url; texLink.style.display = 'inline-block'; }
            else { texLink.style.display = 'none'; }

            pdfBlobUrl = data.url;
            const dlLink = document.getElementById('download-link');
            dlLink.onclick = (e) => {
                e.preventDefault();
                window.open(pdfBlobUrl, '_blank');
            };
            showStep(3);
        } else {
            const msg = data.error || 'Unknown error';
            const logDetail = data.log ? `\n\n${data.log}` : '';
            document.getElementById('review-error-message').textContent = msg + logDetail;
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
    pdfBlobUrl = null;
    document.getElementById('notes').value = '';
    clearImagePreview(); clearBulletinPdf(); clearPrayerPdf();
    clearSlidesPdf();
    clearNotesPdf();
    document.getElementById('outline-summary').innerHTML = '';
    document.getElementById('commentary-cards').innerHTML = '';
    document.getElementById('extract-error-message').textContent = '';
    document.getElementById('extract-error').classList.add('hidden');
    document.getElementById('review-error-message').textContent = '';
    document.getElementById('review-error').classList.add('hidden');
    const dlLink = document.getElementById('download-link');
    dlLink.href = '#';
    dlLink.onclick = null;
    const texLink = document.getElementById('download-tex-link');
    texLink.href = '#';
    texLink.style.display = '';
    document.querySelectorAll('#sermon-form input[type="checkbox"]').forEach(el => {
        el.checked = false;
    });
    document.getElementById('select-all-commentaries').textContent = 'Select all';
    showStep(1);
});

// ─── Collect edited outline from DOM ─────────────────────────────────────────
function collectEditedOutline() {
    const outline = JSON.parse(JSON.stringify(extractedOutline));
    outline.metadata.title    = document.getElementById('edit-title').value.trim() || null;
    outline.metadata.speaker  = document.getElementById('edit-speaker').value.trim() || null;
    outline.metadata.date     = document.getElementById('edit-date').value.trim() || null;
    outline.main_passage      = document.getElementById('edit-passage').value.trim() || outline.main_passage;

    // Point titles and scripture_refs
    document.querySelectorAll('[data-edit-point]:not([data-edit-sub])').forEach(el => {
        const pi = parseInt(el.dataset.editPoint, 10);
        if (!outline.points[pi]) return;
        const field = el.dataset.editField;
        const val = el.textContent.trim();
        if (field === 'scripture_refs') {
            outline.points[pi].scripture_refs = val ? [val] : [];
        } else {
            outline.points[pi].title = val || outline.points[pi].title;
        }
    });

    // Sub-point fields (title and scripture_verse)
    document.querySelectorAll('[data-edit-point][data-edit-sub]').forEach(el => {
        const pi    = parseInt(el.dataset.editPoint, 10);
        const si    = parseInt(el.dataset.editSub, 10);
        const field = el.dataset.editField;
        const sub   = outline.points[pi]?.sub_points[si];
        if (sub !== undefined) {
            const val = el.textContent.trim();
            sub[field] = val || null;
        }
    });

    return outline;
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ─── Init ─────────────────────────────────────────────────────────────────────
checkAuth();
