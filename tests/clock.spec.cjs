const { test, expect } = require('@playwright/test');

// These tests exercise the running browser prototype through real inputs.
// They do not claim native Electron window layering or click-through coverage.
const act = (page, name) => page.locator(`[data-act="${name}"]`);
const digits = page => page.locator('.tube').evaluateAll(tubes => tubes.map(t => t.querySelector('.lit.on')?.dataset.d ?? '_').join(''));
test.beforeEach(async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error' && !msg.text().includes('favicon')) errors.push(msg.text()); });
  page.__errors = errors;
});
test.afterEach(async ({ page }) => { expect(page.__errors).toEqual([]); });
async function open(page) {
  await page.clock.install({ time: new Date('2026-11-17T00:05:00Z') });
  await page.goto('/');
  await page.clock.pauseAt(new Date('2026-11-17T00:05:01Z'));
}
async function inside(page, selector) {
  const b = await page.locator(selector).boundingBox(), v = page.viewportSize();
  expect(b.x).toBeGreaterThanOrEqual(0);
  expect(b.y).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width).toBeLessThanOrEqual(v.width + 1);
  expect(b.y + b.height).toBeLessThanOrEqual(v.height + 1);
}

test('reminder controls preserve an unfinished draft', async ({ page }) => {
  await open(page);
  await page.locator('#k-remind').click();
  await page.locator('#c-time').fill('19:45');
  await page.locator('#c-text').fill('还没写完的中文提醒');
  await act(page, 'water').click();
  await expect(page.locator('#c-text')).toHaveValue('还没写完的中文提醒');
  await expect(page.locator('#c-time')).toHaveValue('19:45');
});

test('settings remain reachable near the screen edge', async ({ page }) => {
  await open(page);
  const b = await page.locator('#rig').boundingBox();
  await page.mouse.move(b.x + 35, b.y + 210);
  await page.mouse.down(); await page.mouse.move(1190, 250); await page.mouse.up();
  await page.locator('#k-set').click();
  await inside(page, '#pop-set');
});

test('six tubes and maximum scale fit a narrow viewport', async ({ page }) => {
  await open(page);
  await page.locator('#k-set').click();
  await act(page, 'seconds').click();
  await page.setViewportSize({ width: 480, height: 700 });
  await inside(page, '#rig');
  await inside(page, '#pop-set');
});

test('countdown survives a reload', async ({ page }) => {
  await open(page);
  await page.locator('#k-remind').click();
  await act(page, 'cd:5').click();
  await page.reload();
  await expect.poll(() => digits(page)).toBe('0500');
});

test('Beijing default, half-hour timezone, DST and 12-hour leading blank', async ({ page }) => {
  await open(page);
  await expect.poll(() => digits(page)).toBe('0805');
  await expect(page.locator('#nameplate')).toHaveCount(0);
  await page.locator('#k-set').click();
  await act(page, 'tz').selectOption('Asia/Kolkata');
  await expect.poll(() => digits(page)).toBe('0535');
  await act(page, 'tz').selectOption('America/New_York');
  await expect.poll(() => digits(page)).toBe('1905');
  await page.clock.setSystemTime(new Date('2026-07-17T00:05:01Z'));
  await page.clock.runFor(100);
  await expect.poll(() => digits(page)).toBe('2005');
  await act(page, 'tz').selectOption('Asia/Shanghai');
  await act(page, 'h24:false').click();
  await expect.poll(() => digits(page)).toBe('_805');
  await act(page, 'seconds').click();
  await expect.poll(() => digits(page)).toBe('_80501');
  await page.reload();
  await expect.poll(() => digits(page)).toBe('_80501');
});

test('date mode automatically returns to the clock', async ({ page }) => {
  await open(page);
  await page.locator('#k-mode').click();
  await expect.poll(() => digits(page)).toBe('1117');
  await page.clock.runFor(5100);
  await expect.poll(() => digits(page)).toBe('0805');
});

test('countdown ends once while preserving the active draft and focus', async ({ page }) => {
  await open(page);
  await page.locator('[data-demo="countdown"]').click();
  await page.locator('#k-remind').click();
  await page.locator('#c-text').fill('会议资料还没写完');
  await page.clock.runFor(12000);
  await expect(page.locator('#c-text')).toHaveValue('会议资料还没写完');
  await expect(page.locator('#c-text')).toBeFocused();
  await expect(page.locator('#bubble')).toHaveText('倒计时结束，时间到！');
  await expect(page.locator('#bubble')).toHaveClass('show');
  await expect(act(page, 'cd:5')).toBeVisible();
  await page.clock.runFor(6000);
  await expect(page.locator('#bubble')).not.toHaveClass('show');
  await page.reload();
  await page.clock.runFor(2000);
  await expect(page.locator('#bubble')).not.toHaveClass('show');
});

for (const [kind, minutes, text] of [['water', 30, '该喝水啦'], ['sit', 45, '坐了好久']]) {
  test(`${kind} reminder uses the elapsed interval across reloads`, async ({ page }) => {
    await open(page);
    await page.locator('#k-remind').click();
    await act(page, `${kind}Every`).selectOption(String(minutes));
    await act(page, kind).click();
    await page.clock.fastForward(10 * 60000);
    await page.reload();
    await page.clock.fastForward((minutes - 10) * 60000);
    await page.clock.runFor(1300);
    await expect(page.locator('#bubble')).toContainText(text);
    await expect(page.locator('#bubble')).toHaveClass('show');
    await page.clock.runFor(6000);
    await expect(page.locator('#bubble')).not.toHaveClass('show');
  });
}

test('hourly chime follows the displayed timezone', async ({ page }) => {
  await open(page);
  await page.clock.setSystemTime(new Date('2026-11-17T00:59:59Z'));
  await page.clock.runFor(2400);
  await expect(page.locator('#bubble')).toHaveText('北京时间 9 点整');
  await expect(page.locator('#bubble')).toHaveClass('show');
});

test('custom reminders persist, fire in sequence, and can be deleted', async ({ page }) => {
  await open(page);
  await page.locator('#k-remind').click();
  for (const text of ['第一条提醒', '第二条提醒']) {
    await page.locator('#c-time').fill('08:06');
    await page.locator('#c-text').fill(text);
    await act(page, 'c-add').click();
    await page.clock.runFor(100);
  }
  await page.reload();
  await page.locator('#k-remind').click();
  await expect(page.locator('#pop-remind')).toContainText('第二条提醒');
  await page.clock.fastForward(60000);
  await page.clock.runFor(1300);
  await expect(page.locator('#bubble')).toHaveText('第一条提醒');
  await page.clock.runFor(6800);
  await expect(page.locator('#bubble')).toHaveText('第二条提醒');
  await page.locator('.row').filter({ hasText: '第二条提醒' }).locator('.del').click();
  await page.reload();
  await page.locator('#k-remind').click();
  await expect(page.locator('#pop-remind')).not.toContainText('第二条提醒');
});

test('pet link switch silences demo reminders', async ({ page }) => {
  await open(page);
  await page.locator('#k-set').click();
  await act(page, 'petLink').click();
  await page.keyboard.press('Escape');
  await page.locator('[data-demo="water"]').click();
  await page.clock.runFor(8000);
  await expect(page.locator('#bubble')).not.toHaveClass('show');
});

test('drag, grip, pinch and keyboard resizing persist without clipping', async ({ page }) => {
  await open(page);
  const start = await page.locator('#rig').boundingBox();
  await page.mouse.move(start.x + 30, start.y + start.height - 35);
  await page.mouse.down(); await page.mouse.move(start.x + 100, start.y + start.height - 85); await page.mouse.up();
  const moved = await page.locator('#rig').boundingBox();
  expect(moved.x).toBeGreaterThan(start.x + 50);
  await page.locator('#grip').focus();
  await page.keyboard.press('ArrowRight');
  const resized = await page.locator('#rig').boundingBox();
  expect(resized.width).toBeGreaterThan(moved.width);
  await page.reload();
  expect((await page.locator('#rig').boundingBox()).width).toBeCloseTo(resized.width, 0);
  const grip = await page.locator('#grip').boundingBox();
  await page.mouse.move(grip.x + 8, grip.y + 8); await page.mouse.down();
  await page.mouse.move(grip.x - 100, grip.y - 50); await page.mouse.up();
  const smaller = await page.locator('#rig').boundingBox();
  expect(smaller.width).toBeLessThan(resized.width);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: smaller.x + 50, y: smaller.y + 50, deltaX: 0, deltaY: 30, modifiers: 2 });
  await expect.poll(async () => (await page.locator('#rig').boundingBox()).width).toBeLessThan(smaller.width);
  await inside(page, '#rig');
  await page.setViewportSize({ width: 320, height: 480 });
  await page.locator('#k-set').click();
  await inside(page, '#pop-set');
  await inside(page, '#rig');
});

test('renders four and six tubes on dark and light backgrounds without missing images', async ({ page }, info) => {
  await open(page);
  await expect(page.locator('img')).toHaveCount(6);
  expect(await page.locator('img').evaluateAll(images => images.every(im => im.complete && im.naturalWidth > 0))).toBe(true);
  await page.screenshot({ path: info.outputPath('four-dark.png'), animations: 'disabled' });
  await page.locator('#k-set').click();
  await act(page, 'seconds').click();
  await page.keyboard.press('Escape');
  await page.locator('[data-wall="light"]').click();
  await page.screenshot({ path: info.outputPath('six-light.png'), animations: 'disabled' });
  await expect(page.locator('.tube')).toHaveCount(6);
  await page.locator('#k-set').click();
  await page.screenshot({ path: info.outputPath('settings.png'), animations: 'disabled' });
});
