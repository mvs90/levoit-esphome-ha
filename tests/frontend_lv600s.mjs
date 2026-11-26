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
add('select.humidifier_mode', 'Humidity', { options: ['Manual', 'Humidity', 'Humidity Sleep', 'Auto (read only)', 'Unknown'] });
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
assert(!html.includes('data-domain="fan"'));
assert(!html.includes('CADR') && !html.includes('PM2.5') && !html.includes('New filter'));
const card = { name: 'humidifier', title: 'Humidifier', model: 'LV600S', controls, online: true };
html = panel._deviceCard(card);
assert(html.includes('data-domain="switch"') && html.includes('switch.power'));
assert(html.includes('Humidity') && !html.includes('data-domain="fan"'));
assert(html.includes('data-humidifier-mode="select.humidifier_mode"'));
assert(html.includes('value="Humidity" selected'));
assert(html.includes('value="Manual"') && html.includes('value="Humidity Sleep"'));
assert(!html.includes('value="Auto (read only)"') && !html.includes('value="Unknown"'));
for (const [level, value] of [[1, 1], [2, 5], [3, 9]]) {
  const button = html.match(new RegExp(`<button[^>]*aria-label="Mist level ${level}"[^>]*>`))[0];
  assert(button.includes('data-entity="number.mist_level"'));
  assert(button.includes(`&quot;value&quot;:${value}`));
  assert(button.includes(`aria-pressed="${level === 2}"`));
}
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
assert(html.includes('Auto (read only)') && !html.includes('&quot;option&quot;:&quot;Auto (read only)&quot;'));
states['select.humidifier_mode'].state = 'Humidity Sleep';
html = panel._deviceCard(card);
assert(html.match(/<button[^>]*aria-label="Mist level 1"[^>]*>/)[0].includes('disabled'));
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
const action = (markup, label) =>
  [...markup.matchAll(/<button\b[^>]*>[^<]*<\/button>/g)].map(([b]) => b)
    .find((b) => b.endsWith('>' + label + '</button>'));
html = panel._devicePage();
assert(action(html, '30 min') && !action(html, '30 min').includes('disabled'));
assert(action(html, 'Cancel').includes('&quot;value&quot;:0'));
states['sensor.timer_remaining_seconds'].state = '125';
const timer = panel._lv600sTimer(false);
assert(timer.includes('Remaining') && timer.includes('125 s'));
assert.match(timer, /<div class="opts" role="group" aria-label="Turn off in"><button class="opt"/);
assert(!timer.includes('class="s-label">Turn off in'));
assert(timer.includes('Adjust minutes'));
assert(action(timer, 'Cancel').includes('class="btn text"'));
states['sensor.timer_remaining_seconds'].state = '0';
assert(!action(panel._lv600sTimer(false), 'Cancel'));
states['binary_sensor.water_tank_empty'].state = 'on';
html = panel._devicePage();
assert(action(html, '30 min').includes('disabled'));
assert(!html.match(/<button[^>]*data-entity="switch.power"[^>]*>/)[0].includes('disabled'));
states['switch.power'].state = 'off';
html = panel._deviceCard(card);
assert(html.includes('Tank in · empty'));
assert(html.match(/class="dc-sub"[^\n]*class="dc-tank warning"/));
assert(html.match(/<button[^>]*data-entity="switch.power"[^>]*>/)[0].includes('disabled'));
assert(html.match(/<button[^>]*aria-label="Mist level 1"[^>]*>/)[0].includes('disabled'));
assert(html.match(/<select[^>]*data-humidifier-mode[^>]*>/)[0].includes('disabled'));
states['binary_sensor.tank_removed'].state = 'on';
html = panel._deviceCard(card);
assert(html.includes('Tank removed') && !html.includes('Tank in · empty'));
states['binary_sensor.tank_removed'].state = 'off';
states['binary_sensor.water_tank_empty'].state = 'off';
assert(panel._deviceCard(card).includes('Tank in · water available'));
states['binary_sensor.water_tank_empty'].state = 'unavailable';
assert(panel._deviceCard(card).includes('Tank in · water level unknown'));
states['binary_sensor.mcu_connection'].state = 'off';
assert(panel._deviceCard(card).includes('Tank status unknown'));
states['binary_sensor.mcu_connection'].state = 'on';
states['binary_sensor.water_tank_empty'].state = 'off';

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
assert.deepEqual(requests[0].entity_ids, ['sensor.humidity', 'sensor.temperature', 'number.mist_level', 'number.warm_level']);
assert.deepEqual(panel._history.data['number.mist_level'].map(([, value]) => value), [1, 5, null, null]);
assert.deepEqual(panel._history.data['number.warm_level'].map(([, value]) => value), [3, 3]);
html = panel._devicePage();
assert(html.indexOf('class="card hero"') < html.indexOf('class="card history"'));
assert(html.indexOf('class="card history"') < html.indexOf('class="sections"'));
assert(html.includes('class="hist-levels"') && html.includes('line c-mist') && html.includes('line c-warm dashed'));
assert(html.includes('100%') && html.includes('-5°C'));
assert(html.includes('7 days') && !html.includes('NaN'));
panel._historyRange = 'week';
await panel._loadHistory();
assert.equal(Date.parse(requests[1].end_time) - Date.parse(requests[1].start_time), 7 * 86400000);

panel._hass.locale = { language: 'de-DE' };
html = panel._deviceCard(card);
assert(html.includes('Tank eingesetzt · Wasser vorhanden'));
assert(html.includes('Nebelstufe 2') && html.includes('value="Humidity" selected>Feuchte'));
html = panel._devicePage();
for (const value of ['Verlauf', '7 Tage', 'Luftfeuchtigkeit', 'Temperatur', 'Nebelstufe', 'Warmnebelstufe']) {
  assert(html.includes(value));
}
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
