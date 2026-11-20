/* Native adapter. The accepted clock renderer remains shared with the browser prototype. */
(() => {
  'use strict';
  const sdk = window.pet, CONFIG = 'clock.config', RUNTIME = 'clock.runtime', PAD = 12;
  let config, runtime, geometry, anchor, app, endSeen = 0, request, lastNotice;
  let writes = Promise.resolve(), scheduled = false, layingOut = false, dirty = false, gesture = null, pollBusy = false;
  const error = err => {
    console.error(err);
    let node = document.getElementById('host-error');
    if (!node) { node = document.createElement('div'); node.id = 'host-error'; node.setAttribute('role', 'alert'); document.body.append(node); }
    node.textContent = '时钟暂时无法连接桌宠，请从插件管理重新打开。' + (err?.message || '');
  };
  const queueWrite = (key, value) => { writes = writes.catch(() => {}).then(() => sdk.storage.set(key, value)).catch(error); return writes; };
  const H = window.NixieHost = {
    ready: (async () => {
      if (['getPanelBounds', 'setPanelBounds', 'setPanelHitRegions'].some(name => typeof sdk?.ui?.[name] !== 'function')) throw Error('辉光管时钟与当前宿主不兼容：缺少桌面窗口支持，请等待兼容版本。');
      [config, runtime, geometry, anchor] = await Promise.all([sdk.storage.get(CONFIG), sdk.storage.get(RUNTIME), sdk.ui.getPanelBounds(), sdk.storage.get('clock.anchor')]);
      if (!geometry) throw Error('面板未就绪');
      anchor = anchor && Number.isFinite(anchor.x) && Number.isFinite(anchor.y) ? anchor : { x: geometry.bounds.x + PAD, y: geometry.bounds.y + PAD };
      request = config?.countdown;
      endSeen = request?.id && request.id !== runtime?.requestId ? request.end : runtime?.countdownEnd || 0;
      lastNotice = runtime?.lastNotice?.id;
      H.initial = { ...config, runtime: { ...runtime, countdownEnd: endSeen } };
    })(),
    maxScale: lay => Math.min(3, (geometry.workArea.width - PAD * 2) / lay.w, (geometry.workArea.height - PAD * 2) / lay.h),
    save: state => {
      if (state.runtime.countdownEnd !== endSeen) {
        endSeen = state.runtime.countdownEnd;
        request = { id: crypto.randomUUID(), end: endSeen };
      }
      return queueWrite(CONFIG, JSON.parse(JSON.stringify({ set: state.set, remind: state.remind, countdown: request })));
    },
    changed() {
      dirty = true;
      if (scheduled || layingOut || !app) return;
      scheduled = true;
      setTimeout(() => { scheduled = false; layout().catch(error); }, 40);
    },
    async close() { await writes; await sdk.ui.closePanel(); },
    start(value) {
      app = value;
      H.changed();
      const clock = document.getElementById('clock');
      clock.addEventListener('pointerdown', e => {
        if (e.button !== 0 || e.target.closest('.knob,.pop')) return;
        gesture = { pointer: e.pointerId, x: e.screenX, y: e.screenY, anchor: { ...anchor }, scale: app.S.set.scale, resize: !!e.target.closest('.grip') };
        clock.setPointerCapture(e.pointerId);
        clock.classList.add(gesture.resize ? 'resizing' : 'dragging');
        sdk.ui.setPanelHitRegions(null).catch(error); e.preventDefault();
      });
      clock.addEventListener('pointermove', e => {
        if (!gesture) return;
        const dx = e.screenX - gesture.x, dy = e.screenY - gesture.y;
        if (gesture.resize) {
          const size = app.size();
          const width = size.w / app.S.set.scale, height = size.h / app.S.set.scale;
          app.setScale(gesture.scale + (dx * width + dy * height) / (width * width + height * height));
        } else { anchor = { x: gesture.anchor.x + dx, y: gesture.anchor.y + dy }; H.changed(); }
      });
      const end = () => {
        if (!gesture) return;
        const pointer = gesture.pointer; gesture = null;
        if (clock.hasPointerCapture(pointer)) clock.releasePointerCapture(pointer);
        clock.classList.remove('dragging', 'resizing'); H.save(app.S); H.changed();
      };
      clock.addEventListener('pointerup', end); clock.addEventListener('pointercancel', end); clock.addEventListener('lostpointercapture', end); window.addEventListener('blur', end);
      setInterval(async () => {
        if (pollBusy) return;
        pollBusy = true;
        try {
          runtime = await sdk.storage.get(RUNTIME);
          if (!runtime) return;
          if (!request?.id || runtime.requestId === request.id) {
            app.S.runtime.countdownEnd = endSeen = runtime.countdownEnd || 0; app.updateCountdown();
          }
          if (runtime.lastNotice?.id !== lastNotice) {
            lastNotice = runtime.lastNotice?.id;
            if (runtime.lastNotice?.roll && Date.now() - runtime.lastNotice.createdAt < 15000) app.roll();
          }
        } catch (e) { error(e); } finally { pollBusy = false; }
      }, 1000);
    }
  };
  async function layout() {
    if (layingOut || !app) return;
    layingOut = true; dirty = false;
    try {
      const current = await sdk.ui.getPanelBounds();
      if (!current) return;
      geometry = current;
      const area = current.workArea, clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
      if (app.S.set.scale > H.maxScale(app.lay())) { app.S.set.scale = Math.floor(H.maxScale(app.lay()) * 100) / 100; app.applyLook(); }
      const { w, h } = app.size();
      anchor.x = clamp(anchor.x, area.x + PAD, area.x + area.width - w - PAD);
      anchor.y = clamp(anchor.y, area.y + PAD, area.y + area.height - h - PAD);
      const pop = document.querySelector('.pop:not([hidden])');
      let px = anchor.x, py = anchor.y, pw = 0, ph = 0;
      if (pop) {
        pw = Math.min(322, area.width - PAD * 2);
        pop.style.width = pw + 'px'; pop.style.maxHeight = Math.max(100, area.height - PAD * 2) + 'px';
        ph = pop.offsetHeight;
        px = clamp(anchor.x + (w - pw) / 2, area.x + PAD, area.x + area.width - pw - PAD);
        if (anchor.y - ph - PAD * 2 >= area.y) py = anchor.y - ph - PAD;
        else if (anchor.y + h + ph + PAD * 2 <= area.y + area.height) py = anchor.y + h + PAD;
        else py = clamp(anchor.y + (h - ph) / 2, area.y + PAD, area.y + area.height - ph - PAD);
      }
      const x = Math.floor(Math.min(anchor.x, px) - PAD), y = Math.floor(Math.min(anchor.y, py) - PAD);
      const width = Math.ceil(Math.max(anchor.x + w, px + pw) + PAD - x), height = Math.ceil(Math.max(anchor.y + h, py + ph) + PAD - y);
      const desired = { x, y, width, height };
      if (Object.keys(desired).some(k => desired[k] !== current.bounds[k])) geometry = await sdk.ui.setPanelBounds(desired);
      const b = geometry.bounds, clock = document.getElementById('clock');
      clock.style.left = anchor.x - b.x + 'px'; clock.style.top = anchor.y - b.y + 'px';
      if (pop) { pop.style.left = px - b.x + 'px'; pop.style.top = py - b.y + 'px'; }
      // Transparent gaps between tubes and outside the wood do not intercept desktop input.
      const rects = [...document.querySelectorAll('.tube,.bulb,.knob,.grip,.pop:not([hidden])')].map(el => {
        const r = el.getBoundingClientRect(); return { x: Math.max(0, r.x), y: Math.max(0, r.y), width: r.width, height: r.height };
      });
      const top = (app.lay().topY - 24) * app.S.set.scale;
      rects.push({ x: anchor.x - b.x + w * .025, y: anchor.y - b.y + top, width: w * .95, height: h - top });
      await sdk.ui.setPanelHitRegions(gesture ? null : rects);
      if (!gesture) await queueWrite('clock.anchor', { ...anchor });
    } finally { layingOut = false; if (dirty) H.changed(); }
  }
})();
