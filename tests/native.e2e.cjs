'use strict';
// Real, isolated hidden Electron. CDP keyboard input proves panel UI -> SDK;
// native z-order, Spaces and actual OS passthrough require visible acceptance.
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const HOST = process.env.PET_PLUGIN_HOST_DIR;
const expectIncompatible = process.argv.includes('--expect-incompatible');
const liveMarket = process.argv.includes('--market');
if (!HOST) throw Error('Set PET_PLUGIN_HOST_DIR to the compatible host demo directory');
const REPO = path.dirname(HOST), H = require(path.join(REPO, 'tests/e2e-helpers'));
const { createMandatoryLoginFixture } = require(path.join(REPO, 'tests/helpers/mandatory-login-fixture'));
const { activateButton, activateClosingButton } = require(path.join(REPO, 'tests/e2e/html-card-input'));
const { port } = require(path.join(REPO, 'server/account/test/helpers/activation-fixture'));
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-pet-nixie-')), profile = path.join(root, 'desktop-pet-profile');
const evidence = path.resolve(__dirname, liveMarket ? '../test-results/native-market' : expectIncompatible ? '../test-results/native-incompatible' : '../test-results/native'); fs.mkdirSync(evidence, { recursive: true }); fs.mkdirSync(profile);
const report = { checks: [], profile, host: HOST }; let child, account, settings, panel, pet, PORT, loggedIn = false;
const save = (p, v) => fs.writeFileSync(p, JSON.stringify(v, null, 2));
const check = (value, name) => { assert.ok(value, name); report.checks.push(name); console.log('PASS', name); };
async function wait(fn, name, timeout = 20000) { const end = Date.now() + timeout; while (Date.now() < end) { const v = await fn(); if (v) return v; await H.sleep(100); } throw Error('Timeout: ' + name); }
async function shot(name) { const { data } = await H.cdp(panel, 'Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(path.join(evidence, name + '.png'), Buffer.from(data, 'base64')); }
async function boot() {
  child = H.launch({ userData: profile, cdpPort: PORT, bootstrap: path.join(REPO, 'tests/helpers/appearance-hidden-bootstrap.js'), args: ['--mute-audio'], env: { ...account.env, PET_E2E_TEST: '1', PET_E2E_RECORD_BOUNDS: '1', PET_PUBLIC_NATIVE_LOG: path.join(evidence, 'native.jsonl') } });
  if (!loggedIn) { await account.login(PORT); loggedIn = true; }
  pet = await H.findTarget(PORT, '/index.html'); await wait(() => H.evalIn(pet, '!!window.petAPI?.openSettings'), 'pet preload');
  await H.evalIn(pet, 'window.petAPI.openSettings("plugins")'); settings = await H.findReadyTarget(PORT, '/settings.html', 'settings');
}
async function readyPanel() {
  panel = await H.findReadyTarget(PORT, '/nixie-clock/panel.html', 'pet');
  await wait(() => H.evalIn(panel, '!!window.__nixie && document.querySelector("#rig").getBoundingClientRect().width>100'), 'clock initialized');
  await H.sleep(500);
  check(!await H.evalIn(panel, '!!document.querySelector("#host-error")'), 'no panel runtime error');
}
async function stop() { if (!child) return; try { await H.stopOwned(child); } finally { fs.appendFileSync(path.join(evidence, 'host.log'), child.log || ''); child = null; } }
(async () => {
 try {
  PORT = await port(); account = await createMandatoryLoginFixture();
  save(path.join(profile, 'config.json'), { character: 'nienie', onboarding: { completed: true }, general: { autoCheckUpdates: false }, relay: { url: '' }, tts: { enabled: false }, behavior: { idleStroll: false, autoSleep: false }, crossScreen: { lanEnabled: false }, plugins: { developerMode: true, registrySources: [], grants: { 'nixie-clock': { granted: ['ui', 'storage', 'scheduler', 'pet'], version: '0.2.0' } } } });
  save(profile + '.environment-selection.json', { environment: 'test' }); save(path.join(profile, 'settings-privacy.json'), { usageStatsEnabled: false });
  await boot();
  const zip = path.resolve(__dirname, '../dist/nixie-clock-0.2.0.zip');
  const sha256 = require('node:crypto').createHash('sha256').update(fs.readFileSync(zip)).digest('hex');
  const install = await H.evalIn(settings, `settings.pluginsInstallZip(${JSON.stringify({path:zip,sha256,expectPermissions:['ui','storage','scheduler','pet']})})`);
  report.installResult = install;
  if (expectIncompatible) {
    const installed = (await H.evalIn(settings, 'settings.pluginsList()')).find(p => p.id === 'nixie-clock');
    report.incompatiblePlugin = installed;
    check(install.ok && installed?.status === 'disabled' && /宿主版本.*0\.33\.0/.test(installed.reason), 'older host disables the installed ZIP with an explicit host-version reason');
    check(await H.waitTargetGone(PORT, '/nixie-clock/panel.html'), 'incompatible ZIP does not open a clock window');
    check((await H.evalIn(settings, 'settings.pluginsRemove("nixie-clock")')).ok, 'disabled plugin remains removable');
    if (liveMarket) {
      const index = await H.evalIn(settings, 'settings.pluginsRegistryList({refresh:true})');
      const entry = index.plugins.find(p => p.id === 'nixie-clock');
      check(index.fetched && entry?.minHostVersion === '0.33.0' && entry?.description.includes('不兼容'), 'actual public registry returns the installation floor and incompatibility disclosure');
      await activateButton(settings, '[data-field="plugin-tab-market"]');
      await wait(() => H.evalIn(settings, 'document.querySelector("[data-market-id=nixie-clock]")?.textContent.includes("不兼容")'), 'visible market incompatibility description');
      check(true, 'market card visibly discloses incompatibility');
      await activateButton(settings, '[data-market-id="nixie-clock"] [data-action="market-install"]');
      await activateButton(settings, '[data-action="market-perm-confirm"]');
      await wait(() => H.evalIn(settings, 'settings.pluginsList().then(list=>list.some(p=>p.id==="nixie-clock"&&p.status==="disabled"&&p.reason.includes("宿主版本")))'), 'market installation disabled by version');
      await activateButton(settings, '[data-field="plugin-tab-installed"]');
      await wait(() => H.evalIn(settings, 'document.querySelector("[data-plugin-id=nixie-clock]")?.textContent.includes("0.33.0")'), 'visible disabled reason');
      check(await H.evalIn(settings, 'document.querySelector("[data-plugin-id=nixie-clock] [data-action=open-plugin-panel]").disabled'), 'actual market download remains disabled with a visible version requirement and disabled open button');
      const { data } = await H.cdp(settings, 'Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(path.join(evidence, 'incompatible-market.png'), Buffer.from(data, 'base64'));
      check((await H.evalIn(settings, 'settings.pluginsRemove("nixie-clock")')).ok, 'market test removes its own disabled installation');
    }
    report.ok = true;
    return;
  }
  check(install.ok, 'installs ZIP through actual host installer with SHA-256 and permission checks');
  await readyPanel();
  const shape = await H.evalIn(panel, '({tubes:document.querySelectorAll(".tube").length,nameplate:!!document.querySelector("#nameplate"),demo:!!document.querySelector("#demo"),pet:!!document.querySelector("#pet"),bg:getComputedStyle(document.querySelector("#desk")).backgroundColor})');
  check(shape.tubes === 4 && !shape.nameplate && !shape.demo && !shape.pet && shape.bg === 'rgba(0, 0, 0, 0)', 'real transparent panel contains clock only, no timezone plate');
  await shot('four-tube');
  await activateButton(panel, '#k-set');
  await activateButton(panel, '[data-act="seconds"]');
  await wait(() => H.evalIn(panel, 'document.querySelectorAll(".tube").length===6'), 'six tubes');
  const before = await H.evalIn(panel, 'pet.ui.getPanelBounds()');
  await H.evalIn(panel, 'document.querySelector("#grip").focus()');
  await H.cdp(panel, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
  await H.cdp(panel, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
  await wait(() => H.evalIn(panel, 'pet.storage.get("clock.config").then(c=>c?.set.scale>1)'), 'scale persisted');
  await H.sleep(500);
  const after = await H.evalIn(panel, 'pet.ui.getPanelBounds()'); check(after.bounds.width > before.bounds.width, 'keyboard resizing changes actual native bounds');
  const fit = await H.evalIn(panel, '[...document.querySelectorAll("#rig,.pop:not([hidden])")].every(e=>{const r=e.getBoundingClientRect();return r.x>=0&&r.y>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1})'); check(fit, 'clock and settings fit native window');
  await shot('six-tube-settings'); await activateButton(panel, '#pop-set [data-act="close"]');
  await activateButton(panel, '#k-remind'); await activateButton(panel, '[data-act="cd:5"]');
  const request = await wait(() => H.evalIn(panel, 'pet.storage.get("clock.config").then(c=>c?.countdown)'), 'countdown saved');
  check(request.end > Date.now() + 240000, 'countdown started by real keyboard input');
  // Compress elapsed time in persisted business state, through the real plugin SDK.
  await H.evalIn(panel, 'pet.storage.get("clock.config").then(c=>pet.storage.set("clock.config",{...c,countdown:{id:"e2e-short",end:Date.now()+4000}}))');
  await H.evalIn(pet, 'window.__nixieNotices=[];petAPI.onPluginPet(d=>{if(d.action==="bubble")window.__nixieNotices.push(d.text)});true');
  await activateButton(panel, '#pop-remind [data-act="close"]'); await activateButton(panel, '#k-set');
  await activateClosingButton(PORT, panel, '[data-act="hide"]'); panel = null;
  await wait(() => H.evalIn(pet, 'window.__nixieNotices.includes("倒计时结束，时间到！")'), 'background notice delivered after closing panel');
  check(true, 'hidden clock continues reminders through real utility process and pet IPC');
  await H.sleep(2000); check(await H.evalIn(pet, 'window.__nixieNotices.filter(x=>x==="倒计时结束，时间到！").length') === 1, 'countdown completes only once');
  await H.evalIn(settings, 'settings.pluginsTogglePanel("nixie-clock")'); await readyPanel();
  check(await H.evalIn(panel, 'window.__nixie.S.runtime.countdownEnd===0 && window.__nixie.S.set.seconds'), 'reopened panel restores runtime and settings');
  const stored = await H.evalIn(panel, 'pet.storage.get("clock.anchor")'); await stop(); await boot(); await readyPanel();
  check(await H.evalIn(panel, 'window.__nixie.S.set.seconds && window.__nixie.S.set.scale>1'), 'fresh host process restores display preferences');
  const anchor = await H.evalIn(panel, 'pet.storage.get("clock.anchor")'); check(Math.abs(anchor.x - stored.x) < 2 && Math.abs(anchor.y - stored.y) < 2, 'fresh process restores screen anchor');
  check((await H.evalIn(settings, 'settings.pluginsRemove("nixie-clock")')).ok, 'external plugin removed through supported host IPC');
  check(await H.waitTargetGone(PORT, '/nixie-clock/panel.html'), 'unload closes owned panel'); panel = null;
  const records = fs.readFileSync(path.join(evidence, 'native.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  check(records.length > 0 && records.every(x => !x.isVisible && !x.isFocused), 'all isolated test windows remained natively hidden');
  report.ok = true;
 } catch (e) { report.ok = false; report.error = e.stack; console.error(e); if (panel) await shot('failure').catch(() => {}); process.exitCode = 1; }
 finally { await stop().catch(console.error); if (account) await account.close(); save(path.join(evidence, 'report.json'), report); console.log('Evidence: ' + evidence); }
})().then(() => process.exit(process.exitCode || 0));
