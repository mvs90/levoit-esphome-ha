import assert from "node:assert/strict";
import test from "node:test";

import { translate } from "../custom_components/levoit_esphome/frontend/localize.js";
import german from "../custom_components/levoit_esphome/frontend/translations/de.js";

const components = new Map();
globalThis.HTMLElement = class {};
globalThis.customElements = {
  get: (name) => components.get(name),
  define: (name, component) => components.set(name, component),
};
globalThis.window = {};
globalThis.document = { documentElement: { lang: "de" } };
await import("../custom_components/levoit_esphome/frontend/levoit-esphome-panel.js");
await import("../custom_components/levoit_esphome/frontend/levoit-esphome-cards.js");

const entity = "fan.fixture";
const fan = {
  entity_id: entity,
  state: "on",
  attributes: { percentage: 50, percentage_step: 25, preset_mode: "Manual", preset_modes: ["Manual", "Sleep", "Auto", "Pet"] },
};
const controls = {
  "fan.fan": entity,
  "sensor.pm25": "sensor.fixture_pm25",
  "number.timer": "number.fixture_timer",
};
const hass = (language) => ({
  locale: { language },
  states: {
    [entity]: fan,
    "sensor.fixture_pm25": { state: "8", attributes: { unit_of_measurement: "µg/m³" } },
    "number.fixture_timer": { entity_id: "number.fixture_timer", state: "0", attributes: { max: 720 } },
  },
});
const component = (tag) => Object.create(components.get(tag).prototype);

test("Home Assistant locale takes precedence with English fallback", () => {
  for (const locale of ["de", "de-DE", "de-AT", "de-CH"]) {
    assert.equal(translate(hass(locale), "Devices"), "Geräte");
  }
  assert.equal(translate(undefined, "Devices"), "Geräte");
  assert.equal(translate(hass("en"), "Devices"), "Devices");
  assert.equal(translate(hass("fr"), "Devices"), "Devices");
  assert.equal(translate(hass("de"), "Device firmware output"), "Device firmware output");
});

test("German frontend messages preserve every named placeholder", () => {
  const placeholders = (message) => new Set(message.match(/\{\w+\}/g) || []);
  for (const [message, translation] of Object.entries(german)) {
    assert.deepEqual(placeholders(translation), placeholders(message), message);
  }
  assert.equal(translate(hass("de"), "Mode of {device}", { device: "Example" }), "Modus von Example");
});

test("sidebar translates devices, presets, groups, timer and all history ranges", () => {
  const panel = component("levoit-esphome-panel");
  Object.assign(panel, {
    _hass: hass("de"),
    _page: { supported: true, controls },
    _histHidden: new Set(),
    _historyRange: "day",
    _groups: { groups: [], purifiers: [] },
  });
  const device = { name: "fixture", title: "<Device & name>", model: "VITAL100S", controls };
  const overview = panel._deviceCard(device);
  assert.match(overview, /aria-label="Modus von &lt;Device &amp; name&gt;"/);
  assert.match(overview, /value="Manual" selected>Manuell</);
  assert.match(overview, /value="Pet">Haustier</);
  assert.match(panel._groupsView(), /Neue Gruppe/);
  const details = panel._devicePage();
  for (const label of ["Kein Timer aktiv", "Verlauf", "12 h", "24 h", "7 Tage", "30 Tage"]) {
    assert.ok(details.includes(label), label);
  }
  panel._hass = hass("en");
  assert.match(panel._deviceCard(device), /value="Manual" selected>Manual</);
  assert.match(panel._devicePage(), /30 days/);
});

test("localized panel and purifier card still send original preset and speed values", async () => {
  const calls = [];
  const input = { value: "Sleep", dataset: { preset: entity }, blur() {} };
  const panel = component("levoit-esphome-panel");
  panel._callService = (...args) => calls.push(args);
  await panel._onChange({ target: { closest: () => input } });
  const card = component("levoit-purifier-card");
  card._hass = { ...hass("de"), callService: (...args) => calls.push(args) };
  card._config = { entity };
  assert.match(card._body(fan), /value="Sleep">Schlaf</);
  card._config.grid_options = { rows: 4, columns: 6 };
  assert.match(card._body(fan), /data-value="Sleep"[^>]*>Schlaf</);
  card._onChange({ target: { closest: () => input } });
  card._onClick({ target: { closest: () => ({ dataset: { act: "speed", value: "2" } }) } });
  assert.deepEqual(calls, [
    ["fan", "set_preset_mode", entity, { preset_mode: "Sleep" }],
    ["fan", "set_preset_mode", { entity_id: entity, preset_mode: "Sleep" }],
    ["fan", "set_percentage", { entity_id: entity, percentage: 50 }],
  ]);
});

test("dashboard card language changes refresh identical device states", () => {
  const card = component("levoit-list-card");
  const saved = { items: "all", title: "My saved title" };
  card._config = saved;
  card._snap = { groups: [], purifiers: [] };
  const output = [];
  card._render = () => output.push(card._body());
  card.hass = hass("de");
  card.hass = hass("de");
  card.hass = hass("en");
  assert.equal(output.length, 2);
  assert.match(output[0], /Keine Levoit-Luftreiniger/);
  assert.match(output[1], /No Levoit purifiers/);
  assert.ok(output.every((html) => html.includes(saved.title)));
  assert.equal(card.constructor.getConfigForm().computeLabel({ name: "controls" }), "Bedienelemente");
});

test("the onboarding wizard translates both install paths and preserves YAML and channel values", () => {
  const panel = component("levoit-esphome-panel");
  const file = "devices/fixture/fixture-builder.yaml";
  const options = {
    models: [{ model: "VITAL100S", title: "Fixture", custom_base: file, variants: [{
      file, title: "original ESP", board: "esp32dev", variant: "original",
    }] }],
    existing: [{ name: "existing-fixture", title: "<Existing & fixture>", model: "VITAL100S", api_key: true }],
    ota_encryption: true,
  };
  Object.assign(panel, {
    _hass: hass("de"),
    _data: { devices: [], pending: [] },
    _add: {
      options, step: "model", model: "VITAL100S", variant: file, existing: null,
      name: "new-fixture", nameCheck: { ok: true, name: "new-fixture" }, channel: "stable",
    },
  });
  const beforeCreate = {
    model: /Welcher Luftreiniger/,
    esp: /Original-ESP/,
    device: /Neues oder bereits in Home Assistant eingerichtetes Gerät/,
    name: /data-value="stable">Stabil/,
    protection: /<dt>API-Verschlüsselung<\/dt>/,
    create: /Erstelle jetzt <code>new-fixture\.yaml<\/code>/,
  };
  for (const [step, label] of Object.entries(beforeCreate)) {
    panel._add.step = step;
    assert.match(panel._wizard(), label, step);
  }
  panel._add.created = { name: "new-fixture", configuration: "new-fixture.yaml" };
  const newDevice = {
    build: /new-fixture\.yaml kompilieren/,
    flash: /Per USB flashen/,
    connect: /Suche nach <code>new-fixture\.local<\/code>/,
  };
  for (const [step, label] of Object.entries(newDevice)) {
    panel._add.step = step;
    assert.match(panel._wizard(), label, step);
  }
  Object.assign(panel._add, {
    step: "install",
    existing: "existing-fixture",
    created: { name: "existing-fixture", configuration: "existing-fixture.yaml", existing: true },
  });
  const install = panel._wizard();
  assert.match(install, /Auf &lt;Existing &amp; fixture&gt; installieren/);
  assert.match(install, /Drahtlos installieren/);
  panel._add.finished = true;
  assert.match(panel._wizard(), /existing-fixture installiert/);
  panel._hass = hass("en");
  assert.match(panel._wizard(), /existing-fixture installed/);
});
