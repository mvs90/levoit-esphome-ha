import assert from "node:assert/strict";
import { test } from "node:test";

let Panel;
globalThis.HTMLElement = class {};
globalThis.customElements = { get: () => null, define: (_name, value) => { Panel = value; } };
await import("../custom_components/levoit_esphome/frontend/levoit-esphome-panel.js");

function fixture() {
  const panel = Object.create(Panel.prototype);
  const controls = {};
  const states = {};
  const services = [];
  function add(key, state, attributes = {}) {
    const entity_id = key.replace(/^text_sensor\./, "sensor.");
    controls[key] = entity_id;
    states[entity_id] = { entity_id, state, attributes };
    return states[entity_id];
  }
  const fan = add("fan.fan", "off", {
    percentage: 0, percentage_step: 100 / 9, preset_modes: ["Manual", "Sleep", "Humidity", "Unknown", "Auto"],
  });
  add("switch.display", "off");
  add("number.humidity_target", "65", { min: 40, max: 80, step: 1 });
  add("number.warm_level", "0", { min: 0, max: 3 });
  add("number.timer", "0", { min: 0, max: 720 });
  add("text_sensor.timer_duration_initial", "Off");
  add("text_sensor.timer_duration_remaining", "Off");
  add("sensor.humidity", "41", { unit_of_measurement: "%" });
  add("sensor.temperature", "21.2", { unit_of_measurement: "°C" });
  add("sensor.mist_level", "0");
  add("binary_sensor.heating_enabled", "off");
  add("binary_sensor.humidifying", "off");
  const water = add("binary_sensor.water_tank_empty", "off");
  const tank = add("binary_sensor.tank_removed", "off");
  const link = add("binary_sensor.mcu_connection", "on");
  panel._hass = { states, locale: { language: "de" }, callService: async (...args) => services.push(args) };
  panel._page = { title: "LV <600S>", model: "LV600S", target_humidity_preset: true, controls, supported: true };
  panel._histHidden = new Set();
  panel._historyRange = "day";
  panel._groupChip = () => "";
  panel._render = () => {};
  const card = { name: "humidifier", title: "Humidifier", model: "LV600S", controls, online: true };
  return { panel, card, fan, water, tank, link, states, services };
}

function button(html, label) {
  const result = html.match(new RegExp(`<button[^>]*aria-label="${label}"[^>]*>`));
  assert(result, label);
  return result[0];
}

test("LV600S uses a single native fan action for each mist, mode and power control", async () => {
  const { panel, card, fan, services } = fixture();
  const detail = panel._devicePage();
  assert(detail.includes("LV &lt;600S&gt;"));
  for (const [level, percentage] of [[1, 1], [2, 50], [3, 100]]) {
    const html = button(detail, "Mist level " + level);
    assert.match(html, /data-domain="fan".*data-service="set_percentage"/s);
    assert(html.includes(`&quot;percentage&quot;:${percentage}`));
    assert(!html.includes("disabled"));
  }
  assert.match(button(detail, "Humidifier: Turn on"), /data-domain="fan".*data-service="turn_on"/s);
  const cardHtml = panel._deviceCard(card);
  assert.match(cardHtml, /data-preset="fan.fan"/);
  assert.match(cardHtml, /value="Humidity">Auto<\/option>/);
  assert.doesNotMatch(cardHtml, /value="Unknown"|value="Auto"|data-humidifier-mode/);
  const select = { value: "Humidity", dataset: { preset: "fan.fan" }, blur() {} };
  await panel._onChange({ target: { closest: (selector) => selector === "select[data-preset]" ? select : null } });
  await panel._callService("fan", "set_percentage", fan.entity_id, { percentage: 50 });
  assert.deepEqual(services, [
    ["fan", "set_preset_mode", { entity_id: "fan.fan", preset_mode: "Humidity" }],
    ["fan", "set_percentage", { entity_id: "fan.fan", percentage: 50 }],
  ]);
  assert.equal(fan.state, "off");
  assert.equal(panel._lv600sRunCommand, undefined);
});

test("tank and MCU status guard startup and preserve the off control", () => {
  const { panel, card, fan, water, tank, link } = fixture();
  assert.match(panel._deviceCard(card), /Water available/);
  water.state = "on";
  assert.match(panel._deviceCard(card), /Water empty/);
  assert.match(button(panel._devicePage(), "Mist level 2"), /disabled/);
  tank.state = "on";
  const detail = panel._devicePage();
  assert.match(detail, /Tank missing/);
  assert.doesNotMatch(detail, /class="dc-tank[^>]*>[^<]*Water empty/);
  assert.match(button(detail, "Humidifier: Turn on"), /disabled/);
  fan.state = "on";
  assert.doesNotMatch(button(panel._devicePage(), "Humidifier: Turn off"), /disabled/);
  link.state = "off";
  assert.doesNotMatch(panel._deviceCard(card), /class="dc-tank /);
});

test("warmth and timer are direct number commands, with stored target editable in standby", () => {
  const { panel, card, states } = fixture();
  const standby = panel._devicePage();
  assert.match(standby, /data-number="number.humidity_target"/);
  assert.match(button(standby, "Warm mist 2"), /data-domain="number".*data-service="set_value"/s);
  assert.match(panel._deviceCard(card), /aria-label="Warm mist: Off" aria-expanded="false"/);
  const queued = states["number.timer"];
  queued.state = "30";
  assert.match(panel._devicePage(), /30 min starts when switched on|30 min[^<]*starts when switched on/);
  assert.match(panel._devicePage(), /data-entity="number.timer"[^>]*&quot;value&quot;:0/);
  panel._page.target_humidity_preset = false;
  assert.match(panel._devicePage(), /data-number="number.humidity_target"[^>]*disabled/);
});

test("LV600S history uses the read-only mist sensor and all four ranges", async () => {
  const { panel } = fixture();
  let request;
  panel._hass.callWS = async (msg) => { request = msg; return {}; };
  await panel._loadHistory();
  assert.equal(request.type, "history/history_during_period");
  assert(request.entity_ids.includes("sensor.mist_level"));
  assert(request.entity_ids.includes("number.warm_level"));
  assert(!request.entity_ids.includes("fan.fan"));
  const html = panel._historyCard();
  for (const label of ["12 h", "24 h", "7 days", "30 days"]) assert(html.includes(label));
  assert(!html.includes("Zeitraum"));
});

test("purifier statistics retain the right axis label and isolated points", async () => {
  const { panel, states } = fixture();
  states["sensor.pm25"] = { state: "3", attributes: {} };
  states["sensor.cadr"] = { state: "70", attributes: {} };
  panel._page = { model: "CORE600S", controls: { "sensor.pm25": "sensor.pm25", "sensor.current_cadr": "sensor.cadr" } };
  let request;
  panel._hass.callWS = async (msg) => { request = msg; return {}; };
  await panel._loadHistory();
  assert.equal(request.type, "recorder/statistics_during_period");
  const series = panel._historySeries();
  const html = panel._plot(series, { range: "day", start: 0, end: 1000, data: {
    "sensor.pm25": [[0, 3]],
    "sensor.cadr": [[0, 70], [500, 90]],
  } });
  assert.match(html, /class="line dot c-pm"/);
  assert.match(html, /CADR \(right axis\)/);
});
