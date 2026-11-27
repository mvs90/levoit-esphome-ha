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

test("mixed group shows the individual humidifier targets alongside air quality", () => {
  const panel = component("levoit-esphome-panel");
  const humidifiers = [
    { entity_id: "fan.fixture_humidifier", title: "Fixture <one>", target: "number.target", humidity: "sensor.humidity" },
    { entity_id: "fan.other_humidifier", title: "Fixture two", target: "number.other_target" },
  ];
  const states = {
    "sensor.fixture_pm25": { state: "8", attributes: { unit_of_measurement: "µg/m³" } },
    "number.target": { state: "62.5" },
    "number.other_target": { state: "unavailable" },
    "sensor.humidity": { state: "43" },
  };
  const group = {
    id: "fixture", name: "Fixture", enabled: true, mode: "auto", members: [entity],
    humidifiers: humidifiers.map((device) => device.entity_id),
    sensors: [{ type: "pm25", entity_id: "sensor.fixture_pm25" }],
    state: { values: { pm25: { value: 8, how: "max", level: 1, sensors: ["sensor.fixture_pm25"] } } },
  };
  Object.assign(panel, {
    _hass: { locale: { language: "de" }, states },
    _groups: { groups: [], automations: [group], purifiers: [], humidifiers },
    _automation: true,
    _view: "groupdetail",
    _detailId: group.id,
    _seen: { ...states },
  });
  const summary = panel._groupCard(group);
  assert.match(summary, /PM2\.5/);
  assert.match(summary, /Fixture &lt;one&gt; · Zielfeuchte 62,5 %/);
  assert.match(summary, /Fixture two · Zielfeuchte —/);
  const detail = panel._groupDetail();
  assert.match(detail, /PM2\.5/);
  assert.match(detail, /Zielfeuchte/);
  assert.match(detail, /Istfeuchte: 43 %/);
  assert.match(detail, /62,5 %/);
  assert.match(detail, /<h2>Geräte<\/h2>[\s\S]+fan\.fixture[\s\S]+Fixture &lt;one&gt;/);
  assert.equal(panel._pageStatesChanged(), false);
  states["number.target"] = { state: "71" };
  assert.equal(panel._pageStatesChanged(), true);
  assert.match(panel._groupDetail(), /71 %/);

  group.members = [];
  group.sensors[0].source = "manual";
  group.entities = { pm25: "sensor.fixture_pm25" };
  assert.equal(panel._historySeries().length, 0);
  assert.doesNotMatch(panel._groupCard(group), /PM2\.5/);
  assert.doesNotMatch(panel._groupDetail(), /PM2\.5|sensor\.fixture_pm25/);
  assert.match(panel._groupDetail(), /71 %/);
});

test("checking a humidifier updates the display list without adding a purifier", async () => {
  const panel = component("levoit-esphome-panel");
  const draft = { members: ["fan.fixture"], humidifiers: [] };
  Object.assign(panel, {
    _view: "group",
    _edit: { draft },
    _setDraft: (field, value) => { draft[field] = value; },
  });
  const input = {
    dataset: { member: "fan.fixture_humidifier", humidifier: "" },
    checked: true, matches: (selector) => selector === "input[data-member]", blur() {},
  };
  await panel._onChange({ target: input });
  assert.deepEqual(draft, { members: ["fan.fixture"], humidifiers: ["fan.fixture_humidifier"] });
  input.checked = false;
  await panel._onChange({ target: input });
  assert.deepEqual(draft, { members: ["fan.fixture"], humidifiers: [] });
});

test("Automations and Purifier groups use separate routes and member rules", () => {
  const panel = component("levoit-esphome-panel");
  const original = { id: "original", name: "Original group", members: [entity], sensors: [], enabled: true };
  const copy = { id: "copy", name: "Automation copy", members: [], humidifiers: ["fan.humidifier"], sensors: [] };
  Object.assign(panel, {
    _groups: { groups: [original], automations: [copy], purifiers: [], humidifiers: [] },
    _hass: { locale: { language: "en" }, states: {} },
    _render: () => {},
  });
  panel.route = { path: "/groups", prefix: "/levoit-esphome" };
  assert.match(panel._groupsView(), /Original group/);
  assert.doesNotMatch(panel._groupsView(), /Automation copy/);
  assert.equal(panel._validGroupMembers(1, 0), false);
  panel.route = { path: "/automations", prefix: "/levoit-esphome" };
  const automations = panel._groupsView();
  assert.doesNotMatch(automations, /Original group|data-field="enabled"/);
  assert.match(automations, /Automation copy/);
  assert.equal(panel._validGroupMembers(0, 1), true);
  assert.equal(panel._validGroupMembers(1, 0), true);
  panel.route = { path: "/automations/copy", prefix: "/levoit-esphome" };
  assert.equal(panel._detailGroup(), copy);
});

test("the Automations editor lists both device types in the same section", () => {
  const panel = component("levoit-esphome-panel");
  Object.assign(panel, {
    _automation: true,
    _groupKey: "new",
    _hass: { locale: { language: "de" }, states: {} },
    _groups: {
      groups: [],
      automations: [],
      purifiers: [{ entity_id: entity, title: "Purifier example", speeds: 4, sensors: [] }],
      humidifiers: [{ entity_id: "fan.humidifier", title: "Humidifier example" }],
    },
    _schedulePreview: () => {},
  });
  const editor = panel._groupEditor();
  const [, rows] = editor.split("<h2>Geräte</h2>");
  const [choices] = rows.split('<div class="card section">');
  assert.match(choices, /Purifier example/);
  assert.match(choices, /data-member="fan\.humidifier" data-humidifier/);
  assert.match(choices, /Humidifier example/);
  assert.match(choices, /Humidifier example[\s\S]+disabled aria-label="Andere Lüfter"[\s\S]+Folgt später/);
  assert.equal(Array.from(choices.matchAll(/aria-label="([^"]+)"/g)).at(-1)[1], "Andere Lüfter");
  assert.doesNotMatch(editor, /<h2>Luftbefeuchter<\/h2>/);

  panel._automation = false;
  panel._edit = null;
  const legacy = panel._groupEditor();
  assert.match(legacy, /<h2>Luftreiniger<\/h2>/);
  assert.doesNotMatch(legacy, /Humidifier example/);
});

test("Automations show air sensors only for purifiers and edit each type independently", () => {
  const panel = component("levoit-esphome-panel");
  const purifierSensor = { entity_id: "sensor.built_in", type: "pm25" };
  const extraSensor = { entity_id: "sensor.extra_pm25", type: "pm25", source: "manual" };
  const sensorState = (id, type) => ({
    entity_id: id, state: "5", attributes: { device_class: type, unit_of_measurement: "µg/m³" },
  });
  Object.assign(panel, {
    _automation: true,
    _groupKey: "new",
    _hass: {
      locale: { language: "de" },
      states: {
        [purifierSensor.entity_id]: sensorState(purifierSensor.entity_id, "pm25"),
        [extraSensor.entity_id]: sensorState(extraSensor.entity_id, "pm25"),
        "sensor.other_pm10": sensorState("sensor.other_pm10", "pm10"),
      },
    },
    _groups: {
      groups: [], automations: [],
      purifiers: [{ entity_id: entity, title: "Purifier", speeds: 4, sensors: [purifierSensor] }],
      humidifiers: [{ entity_id: "fan.humidifier", title: "Humidifier" }],
    },
    _schedulePreview: () => {},
  });
  assert.doesNotMatch(panel._groupEditor(), /Luftqualitätssensoren|ed-add-toggle/);
  panel._setDraft("humidifiers", ["fan.humidifier"]);
  assert.doesNotMatch(panel._groupEditor(), /Luftqualitätssensoren|ed-add-toggle" data-type="pm/);

  panel._setDraft("members", [entity]);
  const section = panel._groupSensorEditor("");
  assert.match(section, /Luftqualitätssensoren/);
  assert.deepEqual([...section.matchAll(/data-action="ed-add-toggle" data-type="([^"]+)"/g)].map((match) => match[1]), [
    "pm1", "pm25", "pm10", "aqi",
  ]);
  assert.doesNotMatch(section, /data-combine/);
  panel._edit.addOpen = "pm25";
  const menu = panel._groupSensorEditor("");
  assert.match(menu, /data-action="ed-add-sensor" data-entity="sensor\.extra_pm25" data-type="pm25"/);
  assert.doesNotMatch(menu, /sensor\.other_pm10|data-action="ed-add-sensor" data-entity="sensor\.built_in"/);
  panel._setDraft("removed_sensors", [purifierSensor.entity_id]);
  assert.match(panel._groupSensorEditor(""), /ed-restore-sensor" data-entity="sensor\.built_in"/);
  panel._setDraft("removed_sensors", []);
  panel._setDraft("sensors", [extraSensor]);
  assert.match(panel._groupSensorEditor(""), /value="max" selected>Schlechtester Sensor<\/option>/);
  panel._setDraft("combine.pm25", "avg");
  assert.match(panel._groupSensorEditor(""), /value="avg" selected>Mittelwert<\/option>/);
  assert.deepEqual(panel._draftPayload().sensors, [extraSensor]);
  assert.equal(panel._draftPayload().combine.pm25, "avg");
  panel._setDraft("members", []);
  assert.doesNotMatch(panel._groupEditor(), /Luftqualitätssensoren/);
  assert.equal(panel._edit.addOpen, false);
  panel._setDraft("members", [entity]);
  assert.match(panel._groupSensorEditor(""), /value="avg" selected>Mittelwert<\/option>/);

  panel._automation = false;
  const legacy = panel._groupSensorEditor("");
  assert.equal([...legacy.matchAll(/data-action="ed-add-toggle"/g)].length, 1);
  assert.match(legacy, /value="max">Höchste<\/option>/);
  assert.match(legacy, /value="median"/);
  assert.match(legacy, /value="min"/);
});

test("the humidity editor uses humidity sensors and keeps its rules separate", () => {
  const panel = component("levoit-esphome-panel");
  const humidifier = {
    entity_id: "fan.humidifier", title: "Humidifier", humidity: "sensor.device_humidity", target: "number.target",
  };
  Object.assign(panel, {
    _automation: true,
    _groupKey: "new",
    _hass: {
      locale: { language: "de" },
      states: {
        "sensor.room_humidity": { state: "45", attributes: { device_class: "humidity", friendly_name: "Room sensor" } },
        "sensor.other_humidity": { state: "55", attributes: { device_class: "humidity", friendly_name: "Other sensor" } },
        "sensor.temperature": { state: "20", attributes: { device_class: "temperature" } },
        "number.target": { state: "58" },
      },
    },
    _groups: { groups: [], automations: [], purifiers: [], humidifiers: [humidifier] },
    _schedulePreview: () => {},
  });
  assert.doesNotMatch(panel._groupEditor(), /Luftfeuchtigkeitssensoren|Nebelstufen/);
  panel._setDraft("humidifiers", [humidifier.entity_id]);
  panel._edit.addOpen = "humidity";
  const editor = panel._groupEditor();
  assert.match(editor, /aria-label="Gruppenmodus"/);
  assert.match(editor, /aria-label="Gruppensteuerung"[^>]+data-field="humidity_control.enabled"/);
  assert.match(editor, /<aside class="ged-aside"/);
  assert.match(editor, /Luftfeuchtigkeitssensoren[\s\S]+Nebelstufen[\s\S]+Wann die Steuerung eingreift[\s\S]+Wenn die Zielfeuchte erreicht ist/);
  assert.match(editor, /data-entity="sensor\.room_humidity"[^>]*>[\s\S]+Room sensor[\s\S]+45 %/);
  assert.match(editor, /class="stype-chips"><span class="schip"><span>Humidifier<\/span>/);
  assert.deepEqual(panel._draftHumiditySensors(), ["sensor.device_humidity"]);
  assert.match(editor, /Niedrigste[\s\S]+Höchste[\s\S]+Stufe 1[\s\S]+Stufe 2[\s\S]+Stufe 3/);
  assert.equal([...editor.matchAll(/data-humidifier-mist=/g)].length, 2);
  assert.doesNotMatch(editor, /humidity-guide/);
  assert.match(editor, /58 %/);
  assert.doesNotMatch(editor, /sensor\.temperature|Luftqualitätssensoren/);
  assert.equal(panel._draftPayload().humidity_control.enabled, false);
  panel._setDraft("humidity_control.sensors", ["sensor.room_humidity", "sensor.other_humidity"]);
  assert.match(panel._groupEditor(), /value="min" selected>Schlechtester Sensor/);
  panel._setDraft("humidity_control.combine", "avg");
  panel._setDraft("humidity_control.member_mist", { [humidifier.entity_id]: [1, 3, 2] });
  assert.deepEqual(panel._humidifierMist(humidifier.entity_id), [1, 3, 2]);
  assert.deepEqual(panel._humidityMistRange(humidifier.entity_id, "high", 3), [1, 2, 3]);
  assert.deepEqual(panel._humidityMistRange(humidifier.entity_id, "low", 2), [2, 2, 2]);
  panel._setDraft("humidity_control.stop_minutes", 4);
  assert.equal(panel._humidityControlError(), "");
  panel._setDraft("humidity_control.start_below", 15);
  assert.match(panel._humidityControlError(), /aufsteigend/);
  panel._setDraft("humidity_control.start_below", 2);
  assert.deepEqual(panel._humidityPoints(panel._edit.draft.humidity_control), [2, 5, 10]);
  panel._setDraft("humidity_control.target", 58);
  assert.deepEqual(panel._humidityPoints(panel._edit.draft.humidity_control), [48, 53, 56, 58]);
  const moved = panel._humidityAt(3, 60);
  assert.deepEqual(panel._humidityPoints(moved), [48, 53, 56, 60]);
  assert.deepEqual(panel._humidityPoints(panel._humidityAt(0, 99)), [53, 53, 56, 58]);
  assert.deepEqual(panel._humidityPoints(panel._humidityAt(3, 0)), [48, 53, 56, 57]);
  panel._setDraft("humidity_control", moved);
  panel._setDraft("humidity_control.enabled", true);
  panel._setDraft("humidity_control.mode", "manual");
  panel._setDraft("humidity_control.manual_level", 2);
  panel._edit.preview = {
    members: [], sensors: [], humidity: [{ entity_id: humidifier.entity_id, target: 60, value: 50, mist: 2, status: "in_control",
      sensors: [{ entity_id: "sensor.room_humidity", value: 45 }, { entity_id: "sensor.other_humidity", value: 55 }] }],
  };
  const manual = panel._groupEditor();
  assert.match(manual, /data-field="humidity_control.manual_level" data-value="2"/);
  assert.match(manual, /Ist 50 % · Ziel 60 %/);
  assert.match(manual, /Mittelwert aus 2|Durchschnitt aus 2|Mittelwert von 2|Durchschnitt von 2/i);
  assert.match(manual, /Nebelstufe 2/);
  assert.match(manual, /data-humidity-point="3"[^>]*[\s\S]+aria-label="Zielfeuchte"/);
  const { humidity_control: settings } = panel._draftPayload();
  assert.deepEqual(settings.sensors, ["sensor.room_humidity", "sensor.other_humidity"]);
  assert.equal(settings.combine, "avg");
  assert.equal(settings.target, 60);
  assert.deepEqual(settings.member_mist[humidifier.entity_id], [1, 3, 2]);
  assert.equal(settings.stop_minutes, 4);
  assert.equal(settings.enabled, true);
  assert.equal(settings.mode, "manual");
  assert.equal(settings.manual_level, 2);
  panel._groups.purifiers = [{ entity_id: entity, title: "Purifier", speeds: 4, sensors: [] }];
  panel._setDraft("members", [entity]);
  const mixed = panel._groupEditor();
  assert.match(mixed, /Gruppensteuerung der Luftreiniger/);
  assert.match(mixed, /Gruppensteuerung der Luftbefeuchter/);
  assert.match(mixed, /Luftqualitätssensoren/);
  assert.match(mixed, /Luftfeuchtigkeitssensoren/);
  panel._setDraft("members", []);
  panel._setDraft("humidifiers", []);
  assert.equal(panel._draftPayload().humidity_control.enabled, false);
  assert.doesNotMatch(panel._groupEditor(), /Luftfeuchtigkeitssensoren/);
});
