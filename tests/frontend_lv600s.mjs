// Rendering smoke tests, with synthetic HA states and no DOM/server/device access.
import assert from 'node:assert/strict';

let Panel;
globalThis.HTMLElement = class {};
globalThis.customElements = { get: () => null, define: (_name, value) => { Panel = value; } };
await import(new URL('../custom_components/levoit_esphome/frontend/levoit-esphome-panel.js', import.meta.url));
const panel = Object.create(Panel.prototype);
const controls = {};
const states = {};
function add(key, state, attributes = {}) {
  const entity_id = key.startsWith('text_sensor.') ? key.replace('text_sensor.', 'sensor.') : key;
  controls[key] = entity_id;
  states[entity_id] = { entity_id, state, attributes };
}
add('switch.power', 'on');
add('switch.display', 'on');
add('sensor.humidity', '42', { unit_of_measurement: '%' });
add('sensor.temperature', '23', { unit_of_measurement: '°C' });
add('select.humidifier_mode', 'Humidity', { options: ['Manual', 'Humidity', 'Humidity Sleep', 'Auto (read only)', 'Unknown', 'Future Mode'] });
for (const key of ['humidity_target', 'mist_level', 'warm_level', 'timer']) {
  add('number.' + key, '1', { min: 0, max: 80, step: 1 });
}
states['number.mist_level'].state = '5';
panel._page = { title: 'LV <600S>', model: 'LV600S', controls, supported: true };
panel._hass = { states };
panel._infoOpen = false;
panel._histHidden = new Set();
panel._historyRange = 'day';
panel._groupChip = () => '';
let html = panel._devicePage();
assert(html.includes('LV &lt;600S&gt;'));
assert(html.includes('Humidity'));
assert(html.includes('data-domain="switch"'));
assert(html.includes('class="card hero"') && html.includes('class="hero-segs"') && html.includes('class="tiles"'));
assert(html.includes('Configuration'));
assert.match(html, />Configuration<\/[^>]+>[\s\S]*?data-number="number.humidity_target"[\s\S]*?data-entity="switch.display"/);
assert(html.includes('aria-label="Humidifier: Turn off"'));
assert(!html.includes('data-domain="fan"'));
assert(!html.includes('CADR') && !html.includes('PM2.5') && !html.includes('New filter'));
const card = { name: 'humidifier', title: 'Humidifier', model: 'LV600S', controls, online: true };
html = panel._deviceCard(card);
assert(!html.match(/^<div[^>]+>/)[0].includes('data-action="navigate"'));
assert.match(html, /class="dc-top" data-action="navigate"/);
assert.match(html, /class="dc-controls humidifier-controls" data-action="none"/);
assert(html.includes('data-domain="switch"') && html.includes('switch.power'));
assert(html.includes('Humidity') && !html.includes('data-domain="fan"'));
assert(html.includes('data-humidifier-mode="select.humidifier_mode"'));
assert(html.includes('value="Humidity" selected>Auto'));
assert(html.includes('value="Manual"') && html.includes('value="Humidity Sleep"'));
assert(!html.includes('value="Auto (read only)"') && !html.includes('value="Unknown"'));
assert(!html.includes('value="Future Mode"'));
const detail = panel._devicePage();
assert.match(html, /class="lv-level lv-warm-picker"/);
assert.match(html, /icon="mdi:heat-wave".*title="Warm mist"/);
assert.match(html, /aria-label="Warm mist: 1" aria-expanded="false"/);
assert(!html.includes('aria-label="Warm mist 2"'));
panel._lv600sWarmPicker = 'number.warm_level';
const expanded = panel._deviceCard(card);
assert.match(expanded, /lv-warm-picker expanded/);
for (const level of ['Off', '1', '2', '3']) assert(expanded.includes(`aria-label="Warm mist ${level}"`));
panel._lv600sWarmPicker = null;
assert.match(detail, /class="lv-level-icon" icon="mdi:scent" aria-hidden="true" title="Mist level"/);
assert.match(detail, /class="lv-level-icon" icon="mdi:heat-wave" aria-hidden="true" title="Warm mist"/);
add('binary_sensor.humidifying', 'on');
add('binary_sensor.heating_enabled', 'off');
let levelIcons = panel._devicePage();
assert.match(levelIcons, /class="lv-level-icon humidifying" icon="mdi:scent"/);
assert.match(levelIcons, /class="lv-level-icon" icon="mdi:thermometer-off"/);
states['binary_sensor.humidifying'].state = 'off';
states['binary_sensor.heating_enabled'].state = 'on';
levelIcons = panel._devicePage();
assert.match(levelIcons, /class="lv-level-icon" icon="mdi:scent-off"/);
assert.match(levelIcons, /class="lv-level-icon heating" icon="mdi:heat-wave"/);
states['switch.power'].state = 'off';
levelIcons = panel._devicePage();
assert.match(levelIcons, /class="lv-level-icon" icon="mdi:scent-off"/);
assert.match(levelIcons, /class="lv-level-icon" icon="mdi:thermometer-off"/);
states['switch.power'].state = 'on';
for (const markup of [html, detail]) {
  assert.equal((markup.match(/aria-label="Mist level \d"/g) || []).length, 3);
  for (const [level, value] of [[1, 1], [2, 5], [3, 9]]) {
    const button = markup.match(new RegExp(`<button[^>]*aria-label="Mist level ${level}"[^>]*>`))[0];
    assert(button.includes('data-entity="number.mist_level"'));
    assert(button.includes(`&quot;value&quot;:${value}`));
    assert(button.includes(`aria-pressed="${level === 2}"`));
  }
}
assert(!html.match(/aria-label="Warm mist (?:Off|\d)"/));
assert.equal((detail.match(/aria-label="Warm mist (?:Off|\d)"/g) || []).length, 4);
for (const level of [0, 1, 2, 3]) {
  const label = level === 0 ? 'Off' : level;
  const button = detail.match(new RegExp(`<button[^>]*aria-label="Warm mist ${label}"[^>]*>`))[0];
  assert(button.includes('data-entity="number.warm_level"'));
  assert(button.includes(`&quot;value&quot;:${level}`));
  assert(button.includes(`aria-pressed="${level === 1}"`));
}
const belowHeader = detail.indexOf('<div class="sections">');
assert.match(detail.slice(0, belowHeader), /aria-label="Mist level 3"[\s\S]*?aria-label="Warm mist 3"/);
assert(!detail.slice(belowHeader).includes("lv-level-options"));
states['select.humidifier_mode'].state = 'Manual';
assert.match(panel._devicePage(), /data-number="number.humidity_target"[^>]*disabled/);
panel._page.target_humidity_preset = true;
assert.doesNotMatch(panel._devicePage(), /data-number="number.humidity_target"[^>]*disabled/);
assert.match(panel._devicePage(), /40–80 % in Auto mode/);
delete panel._page.target_humidity_preset;
states['select.humidifier_mode'].state = 'Humidity';
const modeChanges = [];
panel._callService = async (...args) => modeChanges.push(args);
const dropdown = { value: 'Manual', dataset: { humidifierMode: 'select.humidifier_mode' }, blur() {} };
const change = { target: { closest: (selector) => selector === 'select[data-humidifier-mode]' ? dropdown : null } };
await panel._onChange(change);
assert.deepEqual(modeChanges, [['select', 'select_option', 'select.humidifier_mode', { option: 'Manual' }]]);
dropdown.value = 'Auto (Original)';
await panel._onChange(change);
assert.equal(modeChanges.length, 1);
states['select.humidifier_mode'].state = 'Auto (read only)';
html = panel._devicePage();
assert(html.includes('Appliance status') && html.includes('class="readout">Auto (Original)'));
assert(!panel._deviceCard(card).includes('Auto (Original)'));
states['select.humidifier_mode'].state = 'Unknown';
assert(panel._devicePage().includes('class="readout">Unknown'));
assert(!panel._deviceCard(card).includes('Unknown'));
states['select.humidifier_mode'].state = 'Humidity';
add('text_sensor.humidifier_mode_status', 'Auto (Original)');
assert(panel._devicePage().includes('class="readout">Auto (Original)'));
html = panel._deviceCard(card);
assert(!html.includes('value="Humidity" selected'));
assert(!html.includes('value="Auto (Original)"'));
delete controls['text_sensor.humidifier_mode_status'];
delete states['text_sensor.humidifier_mode_status'];
states['select.humidifier_mode'].state = 'Humidity Sleep';
html = panel._deviceCard(card);
assert(!html.match(/<button[^>]*aria-label="Mist level 1"[^>]*>/)[0].includes('disabled'));
assert(panel._devicePage().match(/<button[^>]*aria-label="Warm mist 3"[^>]*>/)[0].includes('disabled'));
assert(!html.match(/<select[^>]*data-humidifier-mode[^>]*>/)[0].includes('disabled'));
states['select.humidifier_mode'].state = 'Humidity';
states['switch.power'].state = 'unavailable';
html = panel._deviceCard(card);
assert(html.includes('disabled') && html.includes('Offline'));
console.log('LV600S frontend: humidifier page/card, read-only modes, escaping and unavailable controls passed');
states['switch.power'].state = 'on';
add('binary_sensor.mcu_connection', 'on');
add('binary_sensor.water_tank_empty', 'off');
add('binary_sensor.tank_removed', 'off');
add('sensor.timer_remaining_seconds', 'unknown', { unit_of_measurement: 's' });
states['number.timer'].state = 'unknown';
states['number.timer'].attributes.max = 720;
const action = (markup, label) =>
  [...markup.matchAll(/<button\b[^>]*>[^<]*<\/button>/g)].map(([b]) => b)
    .find((b) => b.endsWith('>' + label + '</button>'));
html = panel._devicePage();
assert(action(html, '30 min') && !action(html, '30 min').includes('disabled'));
assert(html.includes('Timer status unavailable.'));
const timerStatus = 'sensor.timer_remaining_seconds';
const startedAt = Date.parse('2026-11-26T14:00:00Z');
const remaining = (seconds, elapsed) => {
  states[timerStatus] = {
    ...states[timerStatus], state: String(seconds),
    last_updated: new Date(startedAt + elapsed * 1000).toISOString(),
  };
};
remaining(0, -1);
panel._updateLv600sTimer();
assert(!action(panel._timerSection({ lv600s: true }), 'Cancel'));
states['switch.power'].state = 'off';
states['number.timer'].state = '2';
const queuedTimer = panel._timerSection({ lv600s: true });
assert.match(queuedTimer, /2 min starts when switched on/);
assert(!queuedTimer.includes('timer-run'));
assert(action(queuedTimer, 'Cancel').includes('&quot;value&quot;:0'));
states['switch.power'].state = 'on';
states['number.timer'].state = '0';
remaining(28800, 0);
panel._updateLv600sTimer();
remaining(14400, 14400);
states['number.timer'].state = '240';
panel._updateLv600sTimer();
const timer = panel._timerSection({ lv600s: true });
assert.match(timer, /class="big">4 h <span class="muted">left of 8 h/);
assert(timer.includes('style="width:50%"'));
assert.match(timer, /<div class="opts" role="group" aria-label="New timer"><button class="opt"/);
assert.deepEqual([...timer.matchAll(/class="opt"[^>]*>([^<]+)<\/button>/g)].map((match) => match[1]),
  ['30 min', '1 h', '2 h', '4 h', '8 h', '12 h']);
assert(!timer.includes('data-number="number.timer"'));
assert(action(timer, 'Cancel').includes('class="btn text"'));
assert(action(timer, 'Cancel').includes('&quot;value&quot;:0'));
add('text_sensor.timer_duration_remaining', '4 h');
add('text_sensor.timer_duration_initial', '8 h');
assert.equal(panel._timerSection(), timer);
remaining('4h 0 min', 14400);
assert.equal(panel._timerSection({ lv600s: true }), timer);
remaining(14400, 14400);
for (const key of ['text_sensor.timer_duration_remaining', 'text_sensor.timer_duration_initial']) {
  delete states[controls[key]];
  delete controls[key];
}

const reopened = Object.create(Panel.prototype);
reopened._page = panel._page;
reopened._render = () => {};
reopened._hass = {
  states,
  callWS: async (command) => {
    assert.deepEqual(command.entity_ids, [timerStatus]);
    return { [timerStatus]: [
      { s: 'unknown', lu: startedAt / 1000 - 1 },
      { s: '28800', lu: startedAt / 1000 },
      { s: '14401', lu: startedAt / 1000 + 14399 },
    ] };
  },
};
reopened._lv600sTimerReading = { state: states[timerStatus], seconds: 14400, at: startedAt + 14400000, total: 0 };
await reopened._restoreLv600sTimer(timerStatus, 14400);
assert.match(reopened._timerSection({ lv600s: true }), /left of 8 h/);
reopened._lv600sTimerReading.total = 0;
reopened._hass.callWS = async () => { throw new Error('History unavailable'); };
await reopened._restoreLv600sTimer(timerStatus, 14400);
const withoutHistory = reopened._timerSection({ lv600s: true });
assert.match(withoutHistory, /class="big">4 h <span class="muted">left<\/span>/);
assert(!withoutHistory.includes('class="bar"'));
remaining(7200, 14401);
panel._updateLv600sTimer();
assert.match(panel._timerSection({ lv600s: true }), /left of 2 h/);
remaining(0, 14402);
panel._updateLv600sTimer();
assert(!action(panel._timerSection({ lv600s: true }), 'Cancel'));
states['binary_sensor.water_tank_empty'].state = 'on';
html = panel._devicePage();
assert(action(html, '30 min').includes('disabled'));
assert(!html.match(/<button[^>]*data-entity="switch.power"[^>]*>/)[0].includes('disabled'));
states['switch.power'].state = 'off';
html = panel._deviceCard(card);
assert(html.includes('title="Water empty"') && html.includes('M9 14h6v2H9Z'));
assert.match(panel._devicePage(), /class="hero-status"[\s\S]*?class="dc-tank warning" title="Water empty"/);
assert(html.match(/class="dc-sub"[^\n]*class="dc-tank warning"/));
assert(html.match(/<button[^>]*data-entity="switch.power"[^>]*>/)[0].includes('disabled'));
assert(html.match(/<button[^>]*aria-label="Mist level 1"[^>]*>/)[0].includes('disabled'));
assert(html.match(/<select[^>]*data-humidifier-mode[^>]*>/)[0].includes('disabled'));
states['binary_sensor.tank_removed'].state = 'on';
html = panel._deviceCard(card);
assert(html.includes('title="Tank missing"') && html.includes('M12 1l4 4'));
assert(!html.includes('Water empty') && !html.includes('Water available'));
assert.match(panel._devicePage(), /class="hero-status"[\s\S]*?class="dc-tank warning" title="Tank missing"/);
states['binary_sensor.tank_removed'].state = 'off';
states['binary_sensor.water_tank_empty'].state = 'off';
assert(panel._deviceCard(card).includes('title="Water available"'));
assert.match(panel._devicePage(), /class="hero-status"[\s\S]*?class="dc-tank water" title="Water available"/);
states['binary_sensor.water_tank_empty'].state = 'unavailable';
assert(!panel._deviceCard(card).includes('class="dc-tank'));
states['binary_sensor.mcu_connection'].state = 'off';
assert(!panel._deviceCard(card).includes('class="dc-tank'));
states['binary_sensor.mcu_connection'].state = 'on';
states['binary_sensor.water_tank_empty'].state = 'off';

// Standby exposes the retained mode as a fresh choice and waits for confirmed power.
assert.match(panel._deviceCard(card), /<option value="" disabled selected>Off<\/option>/);
assert(!panel._deviceCard(card).includes('value="Humidity" selected'));
const wakePanel = Object.create(Panel.prototype);
wakePanel._data = { devices: [card] };
wakePanel._lv600sCommands = new Map();
// The service-order checks below drive acknowledgement explicitly.
wakePanel._lv600sStartPreview = () => ({ sent: false });
const wakeCalls = [];
const wakeErrors = [];
wakePanel._hass = { states, callService: async (...args) => wakeCalls.push(args) };
wakePanel._toast = (message) => wakeErrors.push(message);
const renders = [];
wakePanel._render = () => renders.push(wakePanel._deviceCard(card));
states['select.humidifier_mode'].state = 'Manual';
dropdown.value = 'Humidity';
const selectingMode = wakePanel._onChange(change);
const powerOn = ['switch', 'turn_on', { entity_id: 'switch.power' }];
assert.deepEqual(wakeCalls, [powerOn]);
await wakePanel._callService('number', 'set_value', 'number.mist_level', { value: 9 });
assert.deepEqual(wakeCalls, [powerOn]);
states['switch.power'].state = 'on';
await new Promise(resolve => setTimeout(resolve, 115));
assert.match(renders.at(-1), /class="power small on"/);
assert.deepEqual(wakeCalls, [powerOn, ['select', 'select_option', {
  entity_id: 'select.humidifier_mode', option: 'Humidity',
}]]);
states['select.humidifier_mode'].state = 'Humidity';
states['number.mist_level'].state = '9';
await selectingMode;
assert.match(renders.at(-1), /class="power small on"/);
assert.match(renders.at(-1), /class="seg sm on" aria-label="Mist level 3"/);
assert.match(renders.at(-1), /value="Humidity" selected>Auto/);

// The detail page resolves the same device even without an overview subscription.
wakePanel._page = panel._page;
wakePanel._data = null;
wakeCalls.length = 0;
states['switch.power'].state = 'off';
states['select.humidifier_mode'].state = 'Humidity';
add('text_sensor.humidifier_mode_status', 'Humidity');
const reportedMode = states[controls['text_sensor.humidifier_mode_status']];
const chooseManual = ['select', 'select_option', { entity_id: 'select.humidifier_mode', option: 'Manual' }];
const settle = () => new Promise(resolve => setTimeout(resolve, 115));
const selectingMist = wakePanel._callService('number', 'set_value', 'number.mist_level', { value: 5 });
assert.deepEqual(wakeCalls, [powerOn]);
states['switch.power'].state = 'on';
await settle();
assert.deepEqual(wakeCalls, [powerOn, chooseManual]);
states['select.humidifier_mode'].state = 'Manual';
await settle();
assert.deepEqual(wakeCalls, [powerOn, chooseManual]);
reportedMode.state = 'Manual';
await selectingMist;
assert.deepEqual(wakeCalls, [powerOn, chooseManual, ['number', 'set_value', { entity_id: 'number.mist_level', value: 5 }]]);

wakeCalls.length = 0;
await wakePanel._callService('number', 'set_value', 'number.mist_level', { value: 9 });
assert.deepEqual(wakeCalls, [['number', 'set_value', { entity_id: 'number.mist_level', value: 9 }]]);

wakeCalls.length = 0;
reportedMode.state = 'Humidity Sleep';
await wakePanel._callService('number', 'set_value', 'number.warm_level', { value: 1 });
assert.deepEqual(wakeCalls, []);
const leavingSleep = wakePanel._callService('number', 'set_value', 'number.mist_level', { value: 1 });
assert.deepEqual(wakeCalls, [chooseManual]);
states['binary_sensor.tank_removed'].state = 'on';
await leavingSleep;
assert.deepEqual(wakeCalls, [chooseManual]);
assert.match(wakeErrors.pop(), /did not confirm Manual/);
states['binary_sensor.tank_removed'].state = 'off';
reportedMode.state = 'Humidity';

wakeCalls.length = 0;
states['switch.power'].state = 'off';
await wakePanel._callService('select', 'select_option', 'select.humidifier_mode', { option: 'Unknown' });
states['binary_sensor.tank_removed'].state = 'on';
await wakePanel._callService('number', 'set_value', 'number.mist_level', { value: 1 });
assert.deepEqual(wakeCalls, []);
states['binary_sensor.tank_removed'].state = 'off';
const interrupted = wakePanel._callService('number', 'set_value', 'number.mist_level', { value: 1 });
assert.deepEqual(wakeCalls, [powerOn]);
states['binary_sensor.mcu_connection'].state = 'off';
await interrupted;
assert.deepEqual(wakeCalls, [powerOn]);
assert.equal(wakeErrors.length, 1);
states['binary_sensor.mcu_connection'].state = 'on';

wakeCalls.length = 0;
await wakePanel._callService('number', 'set_value', 'number.warm_level', { value: 0 });
assert.deepEqual(wakeCalls, [['number', 'set_value', { entity_id: 'number.warm_level', value: 0 }]]);
states['switch.power'].state = 'on';
console.log('LV600S mist selection waits for power and Manual, enforces safety, and keeps heat-off non-waking');


// A level and its activity icon must stay on the same requested value while
// Home Assistant delivers the two independent confirmations.
const previewPanel = Object.create(Panel.prototype);
const previewStates = structuredClone(states);
const previewService = [];
previewPanel._hass = {states: previewStates, callService: async (...args) => previewService.push(args)};
previewPanel._data = {devices: [card]};
previewPanel._lv600sCommands = new Map();
previewPanel._render = () => {};
const setPreviewState = (key, value) => { previewStates[card.controls[key]].state = value; };
setPreviewState('switch.power', 'on');
setPreviewState('number.warm_level', '1.0');
setPreviewState('binary_sensor.heating_enabled', 'on');
setPreviewState('text_sensor.humidifier_mode_status', 'Manual');
const warmVisual = (label, icon) => {
  const cardHtml = previewPanel._deviceCard(card);
  assert.match(cardHtml, new RegExp(`aria-label="Warm mist: ${label}"`));
  assert(cardHtml.includes(`icon="${icon}"`));
};
await previewPanel._callService('number', 'set_value', 'number.warm_level', {value: 0});
warmVisual('Off', 'mdi:thermometer-off');
assert.equal(previewStates['number.warm_level'].state, '1.0');
assert.equal(previewStates['binary_sensor.heating_enabled'].state, 'on');
setPreviewState('binary_sensor.heating_enabled', 'off');
assert.equal(previewPanel._lv600sConfirmPreviews(), false);
warmVisual('Off', 'mdi:thermometer-off');
setPreviewState('number.warm_level', '0.0');
assert.equal(previewPanel._lv600sConfirmPreviews(), true);
warmVisual('Off', 'mdi:thermometer-off');

const schedule = globalThis.setTimeout;
let deadline, delay;
try {
  globalThis.setTimeout = (callback, ms) => { deadline = callback; delay = ms; return 0; };
  await previewPanel._callService('number', 'set_value', 'number.warm_level', {value: 1});
} finally {
  globalThis.setTimeout = schedule;
}
warmVisual('1', 'mdi:heat-wave');
assert.equal(delay, 4000);
assert.equal(previewPanel._lv600sConfirmPreviews(), false);
deadline();
warmVisual('Off', 'mdi:thermometer-off');

await previewPanel._callService('switch', 'turn_off', 'switch.power', {});
assert.match(previewPanel._deviceCard(card), /class="power small"[^>]*Turn on/);
assert.equal(previewStates['switch.power'].state, 'on');
setPreviewState('switch.power', 'off');
assert.equal(previewPanel._lv600sConfirmPreviews(), true);
assert.equal(previewPanel._lv600sPreviews.size, 0);
console.log('LV600S previews warm level and icon together, keeps physical state separate, and restores it on timeout');

const previewErrors = [];
previewPanel._toast = (message) => previewErrors.push(message);
setPreviewState('switch.power', 'on');
previewPanel._hass.callService = async () => { throw new Error('test service failure'); };
await previewPanel._callService('switch', 'turn_off', 'switch.power', {});
assert.deepEqual(previewErrors, ['test service failure']);
assert.match(previewPanel._deviceCard(card), /class="power small on"[^>]*Turn off/);
assert.equal(previewPanel._lv600sPreviews.size, 0);
assert.equal(previewPanel._lv600sCommands.size, 0);

let rejectOld;
previewPanel._hass.callService = async (_domain, service) => {
  if (service === 'turn_off') await new Promise((_resolve, reject) => { rejectOld = reject; });
};
const failedOldPower = previewPanel._callService('switch', 'turn_off', 'switch.power', {});
setPreviewState('switch.power', 'off');
await previewPanel._callService('switch', 'turn_on', 'switch.power', {});
const latestPowerPreview = previewPanel._lv600sPreviews.get('switch.power');
assert.equal(latestPowerPreview.values['switch.power'], 'on');
rejectOld(new Error('superseded service failed'));
await failedOldPower;
assert.equal(previewPanel._lv600sPreviews.get('switch.power'), latestPowerPreview);
setPreviewState('switch.power', 'on');
assert(previewPanel._lv600sConfirmPreviews());

// Expire just the visual preview between power and Manual confirmation.
previewService.length = 0;
previewPanel._hass.callService = async (...args) => previewService.push(args);
setPreviewState('switch.power', 'off');
setPreviewState('text_sensor.humidifier_mode_status', 'Humidity');
let expireVisual;
let slowMist;
try {
  globalThis.setTimeout = (callback, ms) => {
    if (ms !== 4000) return schedule(callback, ms);
    expireVisual = callback;
    return 0;
  };
  slowMist = previewPanel._callService('number', 'set_value', 'number.mist_level', {value: 5});
  assert.deepEqual(previewService, [powerOn]);
  setPreviewState('switch.power', 'on');
  await settle();
  assert.deepEqual(previewService, [powerOn, chooseManual]);
  expireVisual();
  assert.equal(previewPanel._lv600sPreviews.size, 0);
  assert(previewPanel._lv600sCommands.has('switch.power'));
  setPreviewState('text_sensor.humidifier_mode_status', 'Manual');
  await slowMist;
} finally {
  globalThis.setTimeout = schedule;
}
assert.deepEqual(previewService, [powerOn, chooseManual,
  ['number', 'set_value', {entity_id: 'number.mist_level', value: 5}]]);
assert.deepEqual(previewErrors, ['test service failure']);

// Optimistic mode and power can be displayed before dependent controls are ready.
previewPanel._page = {...panel._page, target_humidity_preset: false};
previewPanel._historyRange = 'day';
previewPanel._histHidden = new Set();
setPreviewState('switch.power', 'off');
const configDisabled = () => {
  const markup = previewPanel._devicePage();
  return [
    /<input[^>]*data-number="number.humidity_target"[^>]*>/.exec(markup)[0].includes('disabled'),
    /<button[^>]*data-entity="switch.display"[^>]*>/.exec(markup)[0].includes('disabled'),
  ];
};
const transition = previewPanel._callService('select', 'select_option', 'select.humidifier_mode', {option: 'Humidity'});
assert.deepEqual(configDisabled(), [true, true]);
previewPanel._page.target_humidity_preset = true;
assert.deepEqual(configDisabled(), [false, true]);
previewPanel._page.target_humidity_preset = false;
setPreviewState('switch.power', 'on');
await settle();
assert.deepEqual(configDisabled(), [true, true]);
setPreviewState('text_sensor.humidifier_mode_status', 'Humidity');
await transition;
assert.deepEqual(configDisabled(), [false, false]);
assert.equal(previewPanel._lv600sPreviews.size, 0);
console.log('LV600S rollbacks, delayed confirmation and dependent controls passed');

// The remaining controls dispatch directly to the same ESPHome entities as the panel displays.
previewService.length = 0;
const targetSlider = {
  type: 'range', value: '58', dataset: { number: 'number.humidity_target' }, blur() {},
};
const changeTarget = { target: { closest: selector => selector === 'input[data-number]' ? targetSlider : null } };
await previewPanel._onChange(changeTarget);

const clickService = async (markup) => {
  const dataset = Object.fromEntries([...markup.matchAll(/data-(action|domain|service|entity|args)="([^"]*)"/g)]
    .map(([, key, value]) => [key, value.replaceAll('&quot;', '"')]));
  const button = { dataset, closest: () => null };
  await previewPanel._onClick({ target: { closest: selector => selector === '[data-action]' ? button : null } });
};
const displayButton = previewPanel._devicePage().match(/<button[^>]*data-entity="switch.display"[^>]*>/)[0];
await clickService(displayButton);
await clickService(action(timer, '30 min'));
await clickService(action(timer, 'Cancel'));
assert.deepEqual(previewService, [
  ['number', 'set_value', { entity_id: 'number.humidity_target', value: 58 }],
  ['switch', 'turn_off', { entity_id: 'switch.display' }],
  ['number', 'set_value', { entity_id: 'number.timer', value: 30 }],
  ['number', 'set_value', { entity_id: 'number.timer', value: 0 }],
]);

previewService.length = 0;
previewPanel._page.target_humidity_preset = true;
setPreviewState('switch.power', 'off');
setPreviewState('text_sensor.humidifier_mode_status', 'Manual');
assert.deepEqual(configDisabled(), [false, true]);
await previewPanel._onChange(changeTarget);
assert.deepEqual(previewService, [['number', 'set_value', { entity_id: 'number.humidity_target', value: 58 }]]);
console.log('LV600S target, display and timer controls dispatch directly to ESPHome entities');

const requests = [];
panel._render = () => {};
panel._pageName = card.name;
panel._hass.callWS = async (request) => {
  requests.push(request);
  const start = Date.parse(request.start_time) / 1000;
  return {
    'sensor.humidity': [{ s: '42', lu: start }],
    'sensor.temperature': [{ s: '-2.5', lu: start }, { s: '3', lu: start + 400 }],
    'number.mist_level': [{ s: '1', lu: start }, { s: '5', lu: start + 300 }, { s: 'unavailable', lu: start + 600 }],
    'number.warm_level': [{ s: '3', lu: start + 700 }],
  };
};
await panel._loadHistory();
assert.equal(requests[0].type, 'history/history_during_period');
assert.equal(Date.parse(requests[0].end_time) - Date.parse(requests[0].start_time), 86400000);
assert.deepEqual(requests[0].entity_ids, ['sensor.humidity', 'sensor.temperature', 'number.mist_level', 'number.warm_level']);
assert.deepEqual(panel._history.data['number.mist_level'].map(([, value]) => value), [1, 5, null, null]);
assert.deepEqual(panel._history.data['number.warm_level'].map(([, value]) => value), [3, 3]);
html = panel._devicePage();
assert(html.indexOf('class="card hero"') < html.indexOf('class="card history"'));
assert(html.indexOf('class="card history"') < html.indexOf('class="sections"'));
assert(html.indexOf('aria-label="Warm mist 3"') < html.indexOf('class="card history"'));
assert(html.includes('class="hist-levels"') && html.includes('line c-mist') && html.includes('line c-warm dashed'));
assert(html.includes('100%') && html.includes('-5°C'));
assert(html.includes('7 days') && !html.includes('NaN'));
panel._historyRange = 'week';
await panel._loadHistory();
assert.equal(Date.parse(requests[1].end_time) - Date.parse(requests[1].start_time), 7 * 86400000);

panel._hass.locale = { language: 'de-DE' };
html = panel._deviceCard(card);
assert(html.includes('title="Wasser vorhanden"') && !html.includes('Tank eingesetzt'));
states['binary_sensor.water_tank_empty'].state = 'on';
assert(panel._deviceCard(card).includes('title="Wasser leer"'));
states['binary_sensor.tank_removed'].state = 'on';
html = panel._deviceCard(card);
assert(html.includes('title="Tank fehlt"') && !html.includes('Wasser leer'));
states['binary_sensor.tank_removed'].state = 'off';
states['binary_sensor.water_tank_empty'].state = 'off';
html = panel._deviceCard(card);
assert(html.includes('Nebelstufe 2') && html.includes('value="Humidity" selected>Auto'));
html = panel._devicePage();
for (const value of ['Verlauf', '12 h', '7 Tage', '30 Tage', 'Luftfeuchtigkeit', 'Temperatur', 'Nebelstufe', 'Warmnebelstufe']) {
  assert(html.includes(value));
}
panel._historyRange = 'month';
await panel._loadHistory();
assert.equal(Date.parse(requests[2].end_time) - Date.parse(requests[2].start_time), 30 * 86400000);
assert(panel._historyCard().includes('aria-label="Verlauf des Luftbefeuchters, 30 Tage.'));
panel._historyRange = 'half';
await panel._loadHistory();
assert.equal(Date.parse(requests[3].end_time) - Date.parse(requests[3].start_time), 12 * 3600000);
delete panel._hass.locale;

add('text_sensor.error_message', 'No reported MCU fault');
assert(!panel._devicePage().includes('notice warn'));
add('text_sensor.error_message', 'MCU fault <test>');
assert(panel._devicePage().includes('Error: MCU fault &lt;test&gt;'));
panel._page.model = 'VITAL100S';
add('sensor.pm25', '1', { unit_of_measurement: 'µg/m³' });
panel._hass.callWS = async (request) => {
  assert.equal(request.type, 'recorder/statistics_during_period');
  return { 'sensor.pm25': [{ start: Date.parse(request.start_time), mean: 1 }] };
};
await panel._loadHistory();
assert(panel._historyCard().includes('line dot c-pm'));
const purifier = { name: 'purifier', title: 'Purifier', model: 'VITAL100S', controls: {}, online: true, filter_life: 98 };
assert(panel._deviceCard(purifier).includes('class="dc-filter good"'));
assert(!panel._deviceCard(purifier).includes('dc-tank'));
panel._view = 'groupdetail';
panel._page = null;
panel._detailId = 'purifier-group';
panel._detailGroup = () => ({ entities: { pm1: 'sensor.pm1', pm25: 'sensor.pm25' } });
panel._hass.callWS = async (request) => {
  assert.equal(request.type, 'recorder/statistics_during_period');
  const start = Date.parse(request.start_time);
  return {
    'sensor.pm1': [{ start, mean: 10 }],
    'sensor.pm25': [{ start, mean: 20 }],
  };
};
await panel._loadHistory();
html = panel._historyCard();
assert.match(html, /class="line dot c-pm1" d="M0\.0,77\.0h0\.01"/);
assert.match(html, /class="line dot c-pm" d="M0\.0,6\.0h0\.01"/);
console.log('Tank placement, safety guards, German labels, recorder history and purifier rendering passed');
