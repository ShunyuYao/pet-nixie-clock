'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { activate } = require('../plugin/tool');
const methods = ['getPanelBounds', 'setPanelBounds', 'setPanelHitRegions'];

for (const missing of methods) {
  test(`missing ${missing} reports incompatibility before starting reminders or writing data`, async () => {
    const notices = [];
    const fail = () => assert.fail('incompatible plugin must not start work');
    const ui = Object.fromEntries(methods.filter(name => name !== missing).map(name => [name, fail]));
    await assert.rejects(activate({ ui, storage: { get: fail, set: fail }, scheduler: { every: fail }, pet: { bubble: async text => notices.push(text) } }), /不兼容/);
    assert.equal(notices.length, 1);
    assert.match(notices[0], /缺少桌面窗口支持/);
    const window = { pet: { ui, storage: { get: fail } } };
    vm.runInNewContext(readFileSync(require.resolve('../plugin/host.js'), 'utf8'), { window });
    await assert.rejects(window.NixieHost.ready, /不兼容/);
  });
}
