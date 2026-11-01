const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '../artifacts');
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {})});
  const page = await browser.newPage({viewport: {width: 1280, height: 900}});
  const errors = [], dialogs = [], requests = [], results = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('dialog', async d => {dialogs.push(d.message()); await d.dismiss();});
  page.on('request', r => {if (/^https?:/.test(r.url())) requests.push(r.url());});
  try {
    await page.goto(pathToFileURL(path.join(root, 'inspection.html')).href);
    await page.getByRole('heading', {name: 'PostgreSQL Plan Evidence', exact: true}).waitFor();
    assert.equal(await page.locator('tbody tr').count(), 3);
    const inner = await page.locator('tbody tr').nth(2).locator('td').allTextContents();
    assert.deepEqual(inner.slice(2, 7).map(Number), [4, 2, 3, 6, 2]);
    assert.match(await page.locator('body').innerText(), /No performance regression verdict/);
    assert.match(await page.locator('body').innerText(), /were not measured/);
    results.push('loop-aware values and caveats'); console.log('Passed: ' + results.at(-1));
    await page.getByText('Capture provenance', {exact: true}).click();
    assert.equal(await page.locator('details').getAttribute('open'), '');
    assert.match(await page.locator('pre').innerText(), /synthetic_fixture/);
    results.push('expandable provenance'); console.log('Passed: ' + results.at(-1));
    await page.screenshot({path: path.join(root, 'desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert(await page.locator('.scroll').evaluate(el => el.scrollWidth > el.clientWidth));
    await page.screenshot({path: path.join(root, 'mobile.png'), fullPage: true});
    results.push('390px layout with contained table scroll'); console.log('Passed: ' + results.at(-1));
    await page.goto(pathToFileURL(path.join(root, 'probe.html')).href);
    assert.equal(await page.locator('img,script').count(), 0);
    assert.match(await page.locator('body').innerText(), /<script>alert/);
    assert.deepEqual(errors, []); assert.deepEqual(dialogs, []); assert.deepEqual(requests, []);
    results.push('inert text and no remote requests'); console.log('Passed: ' + results.at(-1));
    fs.writeFileSync(path.join(root, 'browser-checks.json'), JSON.stringify({completed: true, checks: results}, null, 2));
  } catch (error) {
    await page.screenshot({path: path.join(root, 'failure.png'), fullPage: true});
    throw error;
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
