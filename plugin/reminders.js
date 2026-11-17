'use strict';
const CONFIG = 'clock.config', RUNTIME = 'clock.runtime';
const defaults = () => ({ set: { tz: 'Asia/Shanghai', h24: true, seconds: false, bright: 1, scale: 1, blink: true, antiPoison: true, petLink: true }, remind: { hourly: true, water: { on: false, every: 45 }, sit: { on: false, every: 60 }, customs: [{ id: 1, time: '18:30', text: '该下班啦，收拾收拾', on: true }] } });
function normalize(input) {
  const d = defaults(), c = input && typeof input === 'object' ? input : {};
  const set = { ...d.set, ...c.set }, remind = { ...d.remind, ...c.remind };
  try { new Intl.DateTimeFormat('en', { timeZone: set.tz === 'system' ? undefined : set.tz }); } catch { set.tz = d.set.tz; }
  for (const k of ['water', 'sit']) remind[k] = { on: !!remind[k]?.on, every: Math.max(1, Math.min(1440, Number(remind[k]?.every) || d.remind[k].every)) };
  remind.customs = (Array.isArray(remind.customs) ? remind.customs : []).filter(c => c && /^([01]\d|2[0-3]):[0-5]\d$/.test(c.time)).slice(0, 64).map(c => ({ id: String(c.id), time: c.time, text: String(c.text || '时间到啦').slice(0, 80), on: !!c.on }));
  return { set, remind, countdown: c.countdown || null };
}
function parts(ms, tz) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: tz === 'system' ? undefined : tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(ms).map(p => [p.type, p.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}`, hour: Number(p.hour) };
}
// Pure transition: the tool persists this state before delivering its next notice.
function advance(config, previous, ms) {
  const c = normalize(config), r = structuredClone(previous || {});
  r.queue = Array.isArray(r.queue) ? r.queue.slice(0, 64) : [];
  r.fired = r.fired && typeof r.fired === 'object' ? r.fired : {};
  const enqueue = (kind, text) => { if (r.queue.length < 64) r.queue.push({ kind, text, createdAt: ms }); };
  if (c.countdown?.id && c.countdown.id !== r.requestId) {
    r.requestId = c.countdown.id;
    r.countdownEnd = Number.isFinite(c.countdown.end) && c.countdown.end > 0 ? c.countdown.end : 0;
  }
  if (r.countdownEnd && ms >= r.countdownEnd) { r.countdownEnd = 0; enqueue('countdown', '倒计时结束，时间到！'); }
  const t = parts(ms, c.set.tz), key = `${c.set.tz}|${t.day}|${t.time}`;
  if (key !== r.minuteKey) {
    const first = !r.minuteKey?.startsWith(c.set.tz + '|'); r.minuteKey = key;
    // No startup/zone-change catch-up storm; an enabled interval/countdown still survives restart.
    if (!first) {
      if (c.remind.hourly && t.time.endsWith(':00') && !r.fired['hourly|' + key]) {
        r.fired['hourly|' + key] = ms;
        const zone = c.set.tz === 'Asia/Shanghai' ? '北京时间' : c.set.tz === 'system' ? '现在' : '时钟时间';
        enqueue('hourly', `${zone} ${t.hour} 点整`);
      }
      for (const item of c.remind.customs) {
        const id = `custom|${c.set.tz}|${t.day}|${item.id}`;
        if (item.on && item.time === t.time && !r.fired[id]) { r.fired[id] = ms; enqueue('custom', item.text); }
      }
    }
  }
  for (const k of ['water', 'sit']) {
    const signature = `${c.remind[k].on}|${c.remind[k].every}`;
    if (r[k + 'Config'] !== signature || !Number.isFinite(r[k]) || r[k] > ms) { r[k] = ms; r[k + 'Config'] = signature; }
    if (c.remind[k].on && ms - r[k] >= c.remind[k].every * 60000) { r[k] = ms; enqueue(k, k === 'water' ? '该喝水啦，辉光管都替你渴了' : '坐了好久，起来走两步吧'); }
  }
  r.fired = Object.fromEntries(Object.entries(r.fired).filter(([, at]) => Number.isFinite(at) && ms - at < 172800000).slice(-256));
  let delivery = null;
  if (r.queue.length && (!r.nextDelivery || ms >= r.nextDelivery || r.nextDelivery > ms + 60000)) {
    const notice = r.queue.shift();
    r.serial = (Number.isFinite(r.serial) ? r.serial : 0) + 1;
    r.lastNotice = { ...notice, id: `${ms}-${r.serial}`, roll: notice.kind !== 'hourly' || c.set.antiPoison };
    r.nextDelivery = ms + 6000;
    if (c.set.petLink) delivery = r.lastNotice;
  }
  return { runtime: r, delivery };
}
module.exports = { CONFIG, RUNTIME, defaults, normalize, parts, advance };
