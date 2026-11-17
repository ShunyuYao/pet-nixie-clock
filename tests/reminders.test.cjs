const test = require('node:test');
const assert = require('node:assert/strict');
const { advance, defaults } = require('../plugin/reminders');
const base = Date.parse('2026-11-17T00:59:59Z');
test('Beijing hour follows configured clock; restarts do not repeat it', () => {
  const c = defaults(); let r = advance(c, null, base).runtime;
  let next = advance(c, r, base + 1000); assert.equal(next.delivery.text, '北京时间 9 点整');
  assert.equal(advance(c, JSON.parse(JSON.stringify(next.runtime)), base + 10000).delivery, null);
});
test('first activation and timezone change do not announce the current hour', () => {
  const c = defaults(); const r = advance(c, null, base + 1000); assert.equal(r.delivery, null);
  c.set.tz = 'UTC'; assert.equal(advance(c, r.runtime, base + 1000).delivery, null);
});
test('countdown completes once across restart, cancellation is acknowledged', () => {
  const c = defaults(); c.countdown = { id: 'request-1', end: base + 5000 };
  let r = advance(c, null, base).runtime;
  let done = advance(c, JSON.parse(JSON.stringify(r)), base + 6000); assert.equal(done.delivery.kind, 'countdown'); assert.equal(done.runtime.countdownEnd, 0);
  assert.equal(advance(c, done.runtime, base + 7000).delivery, null);
  c.countdown = { id: 'request-2', end: 0 }; const cancelled = advance(c, r, base + 6000); assert.equal(cancelled.runtime.requestId, 'request-2'); assert.notEqual(cancelled.delivery?.kind, 'countdown');
});
test('intervals survive restart, change resets deadline, missed intervals coalesce', () => {
  const c = defaults(); c.remind.hourly = false; c.remind.water = { on: true, every: 1 };
  let r = advance(c, null, base).runtime;
  let next = advance(c, JSON.parse(JSON.stringify(r)), base + 3600000); assert.equal(next.delivery.kind, 'water'); assert.equal(next.runtime.queue.length, 0);
  c.remind.water.every = 5; assert.equal(advance(c, next.runtime, base + 3700000).delivery, null);
});
test('simultaneous reminders queue without overwriting and mute preserves visual signals', () => {
  const c = defaults(); c.remind.customs = [{ id: 1, time: '09:00', text: '会议', on: true }]; c.set.petLink = false;
  let r = advance(c, null, base).runtime; const next = advance(c, r, base + 1000);
  assert.equal(next.delivery, null); assert.equal(next.runtime.lastNotice.kind, 'hourly'); assert.equal(next.runtime.queue[0].text, '会议');
  c.set.petLink = true; assert.equal(advance(c, next.runtime, base + 7000).delivery.text, '会议');
});
test('daily reminders do not repeat during a daylight saving fold', () => {
  const c = defaults(); c.set.tz = 'America/New_York'; c.remind.hourly = false; c.remind.customs = [{ id: 8, time: '01:30', text: '检查', on: true }];
  let r = advance(c, null, Date.parse('2026-11-01T05:29:00Z')).runtime;
  let next = advance(c, r, Date.parse('2026-11-01T05:30:00Z')); assert.equal(next.delivery.text, '检查');
  r = advance(c, next.runtime, Date.parse('2026-11-01T06:29:00Z')).runtime;
  assert.equal(advance(c, r, Date.parse('2026-11-01T06:30:00Z')).delivery, null);
});
