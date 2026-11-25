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
panel._page = { title: 'LV <600S>', model: 'LV600S', controls, supported: true };
panel._hass = { states };
panel._infoOpen = false;
panel._groupChip = () => '';
let html = panel._devicePage();
assert(html.includes('LV &lt;600S&gt;'));
assert(html.includes('Humidity'));
assert(html.includes('data-domain="switch"'));
assert(!html.includes('data-domain="fan"'));
assert(!html.includes('CADR') && !html.includes('PM2.5') && !html.includes('New filter'));
for (const label of ['Auto (read only)', 'Unknown']) {
  const button = html.match(new RegExp('<button[^>]*>' + label.replace(/[()]/g, '\\$&') + '</button>'));
  assert(button && button[0].includes('disabled'), label + ' must be read only');
}
html = panel._deviceCard({ name: 'humidifier', title: 'Humidifier', model: 'LV600S', controls, online: true });
assert(html.includes('data-domain="switch"') && html.includes('switch.power'));
assert(html.includes('Humidity') && !html.includes('data-domain="fan"'));
states['switch.power'].state = 'unavailable';
html = panel._deviceCard({ name: 'humidifier', title: 'Humidifier', model: 'LV600S', controls, online: false });
assert(html.includes('disabled') && html.includes('Offline'));
console.log('LV600S frontend: humidifier page/card, read-only modes, escaping and unavailable controls passed');
