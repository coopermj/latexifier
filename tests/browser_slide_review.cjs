// Run against a local development server: BASE_URL=http://127.0.0.1:8001 node tests/browser_slide_review.cjs
// Requires Playwright. API responses are fixtures; live Fable/PDF validation is separate.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined });
    try {
        const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
        const errors = [];
        page.on('pageerror', error => errors.push(String(error)));
        const outline = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/rebels-and-their-redeemer.json')));
        const analysis = { pdf_sha256: 'a'.repeat(64), page_count: 30, items: [
            { id: 'addition-1', kind: 'scripture', reference: 'Habakkuk 3:2', label: 'Mercy', slide: 13, target: 'p1.s2', enabled: true },
            { id: 'addition-2', kind: 'image', label: '<script>throw new Error("unsafe")</script>', slide: 6, target: 'p0', bbox: [0, 0, 1, 1], enabled: true },
        ], unmatched_slides: [24] };
        let extraction, generation;
        await page.route('**/web/extract', async route => {
            extraction = route.request().postDataJSON();
            await route.fulfill({ json: { success: true, outline, candidates: {}, slide_analysis: extraction.slides_pdf ? analysis : null, slide_previews: {} } });
        });
        await page.route('**/web/generate', async route => {
            const body = route.request().postDataJSON();
            if (!body.notes) return route.fulfill({ json: { success: false, error: 'No notes' } });
            generation = body;
            await route.fulfill({ json: { success: true, url: '/download/test/sermon.pdf', tex_url: '/download/test/tex' } });
        });
        await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8001');
        await page.locator('#notes').fill('Rebels and Their Redeemer');
        await page.locator('#slides-pdf').setInputFiles({ name: 'slides.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-test') });
        await page.locator('#slides-file-name').filter({ hasText: /^slides.pdf$/ }).waitFor();
        await page.locator('#extract-btn').click();
        await page.locator('#slide-review').waitFor({ state: 'visible' });
        assert.equal(Buffer.from(extraction.slides_pdf, 'base64').toString(), '%PDF-test');
        assert.equal(await page.locator('.slide-addition').count(), 2);
        assert.match(await page.locator('.slide-unmatched').textContent(), /24/);
        assert.equal(await page.locator('#slide-review script').count(), 0);
        await page.locator('[data-slide-index="1"]').uncheck();
        await page.locator('[data-slide-target="0"]').selectOption('p2.s1');
        await page.setViewportSize({ width: 390, height: 844 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        await page.locator('#generate-btn').click();
        await page.locator('#step-3').waitFor({ state: 'visible' });
        assert.equal(generation.slide_analysis.items[0].target, 'p2.s1');
        assert.equal(generation.slide_analysis.items[1].enabled, false);
        assert.equal(generation.slides_pdf, extraction.slides_pdf);
        await page.locator('#start-over-btn').click();
        assert.equal(await page.locator('#slides-pdf').inputValue(), '');
        assert.equal(await page.locator('#slide-review').textContent(), '');
        await page.locator('#notes').fill('Second sermon');
        await page.locator('#extract-btn').click();
        await page.locator('#step-2').waitFor({ state: 'visible' });
        assert.equal(extraction.slides_pdf, null);
        assert.equal(await page.locator('#slide-review').isVisible(), false);
        await page.locator('#back-btn').click();
        await page.locator('#slides-pdf').setInputFiles({ name: 'wrong.txt', mimeType: 'text/plain', buffer: Buffer.from('wrong') });
        await page.locator('#extract-error').waitFor({ state: 'visible' });
        assert.match(await page.locator('#extract-error-message').textContent(), /PDF/);
        assert.equal(await page.locator('#slides-pdf').inputValue(), '');
        assert.deepEqual(errors, []);
        console.log('PASS: upload, review without commentary, escaped content, reassignment, exclusion, mobile layout, generation payload, Start Over, no-slide flow, invalid upload; no browser errors.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
