'use strict';
const { CONFIG, RUNTIME, defaults, advance } = require('./reminders');
module.exports.activate = async pet => {
  let active = true, busy = false, current = await pet.storage.get(RUNTIME), pending = Promise.resolve();
  if (!await pet.storage.get(CONFIG)) await pet.storage.set(CONFIG, defaults());
  const tick = () => {
    if (!active || busy) return pending;
    busy = true;
    pending = (async () => {
      const config = await pet.storage.get(CONFIG);
      if (!active) return;
      const { runtime, delivery } = advance(config, current, Date.now());
      if (JSON.stringify(runtime) !== JSON.stringify(current)) await pet.storage.set(RUNTIME, runtime);
      current = runtime;
      if (active && delivery) await pet.pet.bubble(delivery.text, 5200);
    })().catch(error => console.error('Nixie reminder:', error.message)).finally(() => { busy = false; });
    return pending;
  };
  await tick();
  const timer = await pet.scheduler.every(1000, tick);
  if (typeof pet.ui.getPanelBounds === 'function' && typeof pet.ui.setPanelHitRegions === 'function') {
    if (!await pet.ui.getPanelBounds()) await pet.ui.openPanel();
  } else {
    await pet.pet.bubble('辉光管时钟需要支持桌面悬浮面板的新版宿主。', 7000);
  }
  return { dispose: async () => { active = false; await pet.scheduler.cancel(timer); await pending; } };
};
