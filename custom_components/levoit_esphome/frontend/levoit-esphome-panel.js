// Levoit ESPHome sidebar panel: every device with versions, channel, filter,
// compile and upload. Plain web component, no build step; data comes from the
// integration's WebSocket commands (levoit_esphome/*), admins only.

const INTEGRATION_PAGE = "/config/integrations/integration/levoit_esphome";

// The version this code was loaded as (panel.py adds ?v=<version>). A browser
// defines the page element once per session, so after an update the old code
// keeps running until the page is reloaded; the page then says so.
const LOADED_VERSION = (/[?&]v=([^&#]+)/.exec(import.meta.url) || [])[1] || null;

const KIND_LABELS = {
  original: "Original ESP",
  xiao_c3: "XIAO ESP32-C3",
  c3: "ESP32-C3",
  s3: "XIAO ESP32-S3",
  custom: "Custom config",
};
const BUILD_STEP_LABELS = {
  template: "Updating config…",
  waiting: "Waiting for another build…",
  compile: "Compiling…",
  upload: "Uploading…",
};
const CHANNEL_LABELS = {
  stable: "Stable",
  main: "Main",
  pinned: "Pinned",
  local: "Local",
};

const ICONS = {
  menu: "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",
  refresh:
    "M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z",
  builder:
    "M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z",
  plus: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  purifier:
    "M16,2H8A2,2 0 0,0 6,4V20A2,2 0 0,0 8,22H16A2,2 0 0,0 18,20V4A2,2 0 0,0 16,2M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4M16,20H8V18H16V20M16,16H8V14H16V16M16,12H8V10H16V12Z",
  back: "M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z",
  power:
    "M16.56,5.44L15.11,6.89C16.84,7.94 18,9.83 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12C6,9.83 7.16,7.94 8.88,6.88L7.44,5.44C5.36,6.88 4,9.28 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,9.28 18.64,6.88 16.56,5.44M13,3H11V13H13",
  open: "M14,3V5H17.59L7.76,14.83L9.17,16.24L19,6.41V10H21V3M19,19H5V5H12V3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V12H19V19Z",
  chevron: "M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z",
};

// Small outline drawings per purifier family for the overview (48 x 48, drawn
// in the theme's colours; no product photos). Stroke-only shapes plus a wash.
const DEVICE_SHAPES = {
  // Core 200S-600S: a round column with a top grille
  core: `<rect x="14" y="7" width="20" height="35" rx="8"/><path d="M18 12.5h12M18 16h12M18 19.5h12"/><circle cx="24" cy="31" r="2.2"/>`,
  // Eleva 300X: a squat round body with rings on top
  eleva: `<path d="M11 19v17c0 3.3 5.8 6 13 6s13-2.7 13-6V19"/><ellipse cx="24" cy="19" rx="13" ry="5"/><ellipse cx="24" cy="19" rx="7" ry="2.6"/>`,
  // Vital, Everest Air: a rectangular tower
  tower: `<rect x="13" y="6" width="22" height="37" rx="4"/><path d="M17 11h14M17 14.5h14"/><rect x="18" y="22" width="12" height="14" rx="2"/>`,
  // Sprout: a bell with a base
  sprout: `<path d="M15 39c0-13 3.5-26 9-26s9 13 9 26z"/><path d="M12 42h24"/><circle cx="24" cy="10" r="2"/>`,
  // Superior 6000S: a humidifier with a drop on top
  humidifier: `<rect x="12" y="15" width="24" height="28" rx="7"/><path d="M24 4.5c3.2 4 4.4 6.4 4.4 8.2a4.4 4.4 0 0 1-8.8 0c0-1.8 1.2-4.2 4.4-8.2z"/><path d="M17 33h14"/>`,
  // Philips: a rounded block with a fan
  philips: `<rect x="11" y="9" width="26" height="34" rx="10"/><circle cx="24" cy="19" r="5"/><path d="M18 34h12"/>`,
};
const deviceShape = (model) => {
  const m = model || "";
  if (m.startsWith("CORE")) return "core";
  if (m === "ELEVA300X") return "eleva";
  if (m.startsWith("VITAL") || m === "EVERESTAIR") return "tower";
  if (m === "SPROUT") return "sprout";
  if (m === "SUPERIOR6000S") return "humidifier";
  if (m.startsWith("AC0")) return "philips";
  return "core";
};
const deviceImage = (model) =>
  `<svg class="dev-img" viewBox="0 0 48 48" aria-hidden="true">${DEVICE_SHAPES[deviceShape(model)]}</svg>`;

// "2h 30 min", "45 min", "1h 5 min 10 s" -> seconds; anything else -> 0
const parseDuration = (text) => {
  if (!text) return 0;
  const part = (re) => {
    const m = re.exec(text);
    return m ? Number(m[1]) : 0;
  };
  return part(/(\d+)\s*h/) * 3600 + part(/(\d+)\s*min/) * 60 + part(/(\d+)\s*s\b/);
};

const formatMinutes = (minutes) => {
  const m = Math.round(minutes);
  if (m < 60) return `${m} min`;
  return m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`;
};

const formatNumber = (value) =>
  Number.isInteger(value) ? String(value) : String(Math.round(value * 10) / 10);

// Device page history: Home Assistant's statistics (the sensors have a
// state_class), 5-minute means for a day, hourly means for a week.
const HISTORY_RANGES = {
  day: { label: "24 h", ms: 24 * 3600e3, period: "5minute", step: 5 * 60e3 },
  week: { label: "7 days", ms: 7 * 24 * 3600e3, period: "hour", step: 3600e3 },
};
const HISTORY_REFRESH_MS = 5 * 60e3;
// one small chart each, on a shared time axis: different units, never one axis
const HISTORY_SERIES = [
  { key: "sensor.pm25", title: "PM2.5" },
  { key: "sensor.aqi_index", title: "AQI" }, // Eleva: the 0-500 index
  { key: "sensor.aqi", title: "AQI" }, // the others: the level (only without an index)
  { key: "sensor.current_cadr", title: "CADR" },
];
// plot geometry in viewBox units; the plot stretches to the card's width
// (preserveAspectRatio none), so all text is HTML beside and under it
const CHART = { width: 600, height: 76, top: 6, bottom: 6 };

// a round axis maximum at or above value: 1, 2, 2.5, 5 x 10^n
const niceMax = (value) => {
  if (!(value > 0)) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * magnitude >= value) return m * magnitude;
  return 10 * magnitude;
};

// 22.5 -> "22:30" and back (quiet period hours after midnight)
const hoursToTime = (hours) => {
  const total = Math.round(hours * 60) % (24 * 60);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
};
const timeToHours = (time) => {
  const [h, m] = time.split(":").map(Number);
  return h + (m || 0) / 60;
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const icon = (name) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name]}"></path></svg>`;

class LevoitEsphomePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._busy = new Set(); // device names with a request in flight
    this._checking = false;
    this._unsub = null;
    this._subscribing = false;
    this._deferred = false;
    this._log = null; // the build log dialog: {name, title, lines, building}
    // device page (route /levoit-esphome/<name>): which entity is which setting
    this._route = null;
    this._view = "overview"; // overview, config or device
    this._pageName = null;
    this._page = null; // levoit_esphome/device_controls result
    this._pageError = null;
    this._pageLoading = false;
    this._seen = {}; // entity_id -> state object last rendered
    this._infoOpen = true; // the device page's Info section: open until closed
    // device page history: {name, range, start, end, at, data: {entity_id: [[t, v]]}}
    this._history = null;
    this._historyRange = "day";
    this._historyLoading = false;
    this._historyError = null;
    this._hoverT = null; // time under the crosshair
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    // an overview card is a link: Enter or Space opens the device
    this.shadowRoot.addEventListener("keydown", (ev) => {
      const card = ev.target?.closest?.(".dcard");
      if (card && ev.target === card && (ev.key === "Enter" || ev.key === " ")) {
        ev.preventDefault();
        this._navigate(card.dataset.path);
      }
    });
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    this.shadowRoot.addEventListener("focusout", () => {
      if (this._deferred) {
        this._deferred = false;
        this._render();
      }
    });
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._unsub && !this._subscribing) this._subscribe();
    if (this._pageName && !this._page && !this._pageLoading && !this._pageError) this._loadPage();
    if (
      this._page &&
      this._history &&
      !this._historyLoading &&
      Date.now() - this._history.at > HISTORY_REFRESH_MS
    )
      this._loadHistory();
    // the device page shows live states: render when one of its entities changed
    if (first || this._pageStatesChanged()) this._render();
  }

  // Routes under the panel: "" the device overview, "/config" updates and
  // configs, "/device/<name>" a device's page ("/<name>" from 0.6.x too).
  set route(route) {
    this._route = route;
    const parts = (route?.path || "").split("/").filter(Boolean).map(decodeURIComponent);
    let name = null;
    if (parts[0] === "config") this._view = "config";
    else if (parts[0] === "device" && parts[1]) name = parts[1];
    else if (parts[0]) name = parts[0];
    if (name) this._view = "device";
    else if (parts[0] !== "config") this._view = "overview";
    if (name !== this._pageName) {
      this._pageName = name;
      this._page = null;
      this._pageError = null;
      this._seen = {};
      this._history = null;
      this._historyError = null;
      this._hoverT = null;
      if (name && this._hass) this._loadPage();
    }
    this._render();
  }

  get _base() {
    return this._route?.prefix || "/levoit-esphome";
  }

  async _loadPage() {
    const name = this._pageName;
    this._pageLoading = true;
    try {
      const page = await this._hass.callWS({ type: "levoit_esphome/device_controls", name });
      if (name === this._pageName) {
        this._page = page;
        if (!this._history && !this._historyLoading) this._loadHistory();
      }
    } catch (err) {
      if (name === this._pageName) this._pageError = err?.message || String(err);
    } finally {
      this._pageLoading = false;
      this._render();
    }
  }

  // the entities shown live: the open device's, or every device's on the overview
  _watched() {
    if (this._view === "device") return Object.values(this._page?.controls || {});
    if (this._view === "overview")
      return (this._data?.devices || []).flatMap((d) => Object.values(d.controls || {}));
    return [];
  }

  _pageStatesChanged() {
    if (!this._hass) return false;
    return this._watched().some((entityId) => this._hass.states[entityId] !== this._seen[entityId]);
  }

  _devicePath(name) {
    return `${this._base}/device/${encodeURIComponent(name)}`;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._render();
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    if (this._hass && !this._unsub && !this._subscribing) this._subscribe();
    this._render();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub.then((unsub) => unsub()).catch(() => {});
      this._unsub = null;
    }
  }

  async _subscribe() {
    this._subscribing = true;
    try {
      // re-subscribes by itself after a reconnect
      this._unsub = this._hass.connection.subscribeMessage(
        (data) => {
          this._data = data;
          this._error = null;
          // devices changed (one came online, a config was read): find the
          // open device page's entities again
          if (this._pageName && this._page && !this._pageLoading) this._loadPage();
          this._render();
        },
        { type: "levoit_esphome/subscribe" },
      );
      await this._unsub;
    } catch (err) {
      this._unsub = null;
      this._error = err?.message || String(err);
      this._render();
    } finally {
      this._subscribing = false;
    }
  }

  // --- actions ----------------------------------------------------------------

  _navigate(path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  _toast(message) {
    this.dispatchEvent(
      new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }),
    );
  }

  _device(name) {
    return (
      this._data?.devices.find((d) => d.name === name) ||
      (this._data?.pending || []).find((p) => p.name === name)
    );
  }

  async _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target) return;
    const { action, name, path } = target.dataset;
    if (target.tagName === "A") ev.preventDefault();
    switch (action) {
      case "menu":
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
        break;
      case "navigate":
        this._navigate(path);
        break;
      case "reload":
        location.reload();
        break;
      case "log":
        await this._showLog(name);
        break;
      case "close-log":
        // a click inside the dialog bubbles to the backdrop: close only on the
        // backdrop itself or on the Close button
        if (target.classList.contains("backdrop") && ev.target !== target) break;
        this._log = null;
        this._render();
        break;
      case "retry":
        this._error = null;
        this._render();
        this._subscribe();
        break;
      case "check":
        await this._check();
        break;
      case "compile":
        await this._build(name, false);
        break;
      case "upload":
        await this._build(name, true);
        break;
      case "svc":
        // a device page control: a Home Assistant service on one entity
        if (target.dataset.confirm && !confirm(target.dataset.confirm)) break;
        await this._callService(
          target.dataset.domain,
          target.dataset.service,
          target.dataset.entity,
          JSON.parse(target.dataset.args || "{}"),
        );
        break;
      case "history-range":
        if (target.dataset.range !== this._historyRange) {
          this._historyRange = target.dataset.range;
          this._hoverT = null;
          this._render(); // the old chart stays, dimmed, until the new data is in
          this._loadHistory();
        }
        break;
      case "toggle-info":
        ev.preventDefault(); // the open state is ours, not the <details> element's
        this._infoOpen = !this._infoOpen;
        this._render();
        break;
      case "page-retry":
        this._pageError = null;
        this._page = null;
        this._render();
        this._loadPage();
        break;
    }
  }

  async _callService(domain, service, entityId, args) {
    try {
      await this._hass.callService(domain, service, { entity_id: entityId, ...args });
    } catch (err) {
      this._toast(`${err.message || err}`);
    }
  }

  async _check() {
    this._checking = true;
    this._render();
    try {
      await this._hass.callWS({ type: "levoit_esphome/check" });
    } catch (err) {
      this._toast(`Check failed: ${err.message || err}`);
    } finally {
      this._checking = false;
      this._render();
    }
  }

  async _build(name, upload) {
    const device = this._device(name);
    if (!device) return;
    if (
      upload &&
      !confirm(
        `Compile ${device.title} in the ESPHome Device Builder and upload it over the air?` +
          (device.config_kind && device.config_kind !== "custom"
            ? "\n\nIts template config is refreshed from the newest builder file first."
            : ""),
      )
    )
      return;
    this._busy.add(name);
    this._render();
    try {
      await this._hass.callWS({ type: "levoit_esphome/build", name, upload });
      this._toast(upload ? `${device.title}: compiled and uploaded` : `${device.title}: compiled`);
    } catch (err) {
      this._toast(`${device.title}: ${err.message || err}`);
    } finally {
      this._busy.delete(name);
      this._render();
    }
  }

  async _onChange(ev) {
    const input = ev.target.closest("input[data-number]");
    if (input) {
      // device page slider or time: set the number entity
      const value = input.type === "time" ? timeToHours(input.value) : Number(input.value);
      input.blur(); // let the page render the new value
      await this._callService("number", "set_value", input.dataset.number, { value });
      if (input.dataset.also)
        await this._callService("number", "set_value", input.dataset.also, { value });
      return;
    }
    const select = ev.target.closest("select[data-channel]");
    if (!select) return;
    const device = this._device(select.dataset.channel);
    const channel = select.value;
    if (!device || channel === device.channel) return;
    if (
      device.configuration &&
      !confirm(
        `Switch ${device.title} to ${CHANNEL_LABELS[channel]}?\n\n` +
          `This sets ref: ${channel} in ${device.configuration}; the next update builds from it.`,
      )
    ) {
      select.value = device.channel;
      return;
    }
    this._busy.add(device.name);
    this._render();
    try {
      await this._hass.callWS({
        type: "levoit_esphome/set_channel",
        name: device.name,
        channel,
      });
    } catch (err) {
      this._toast(`${device.title}: ${err.message || err}`);
    } finally {
      this._busy.delete(device.name);
      this._render();
    }
  }

  // --- rendering --------------------------------------------------------------

  _time(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    const lang = this._hass?.locale?.language || this._hass?.language;
    const sameDay = date.toDateString() === new Date().toDateString();
    return sameDay
      ? date.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })
      : date.toLocaleString(lang, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
  }

  _status(d) {
    if (d.building)
      return `<span class="chip info"><span class="spinner"></span>${
        BUILD_STEP_LABELS[d.build_step] || "Building…"
      }</span>`;
    if (d.online === false) return `<span class="chip">Offline</span>`;
    if (!d.configuration) return `<span class="chip">No config</span>`;
    if (d.update_available) return `<span class="chip warning">Update available</span>`;
    if (d.installed && d.latest) return `<span class="chip success">Up to date</span>`;
    return `<span class="chip">Unknown</span>`;
  }

  _lastBuild(d) {
    const logLink = d.has_build_log
      ? ` · <a href="#" data-action="log" data-name="${esc(d.name)}">Log</a>`
      : "";
    const last = d.last_build;
    if (d.building) return logLink ? `<div class="sub">${logLink.slice(3)}</div>` : "";
    if (!last) return "";
    const when = esc(this._time(last.at));
    if (last.ok)
      return `<div class="sub ok">${last.upload ? "Uploaded" : "Compiled"} ${when}${logLink}</div>`;
    const what = last.upload ? "Compile and upload" : "Compile";
    return `<div class="sub bad" title="${esc(last.error)}">${what} failed ${when}${logLink}: ${esc(
      last.error,
    )}</div>`;
  }

  _channel(d) {
    const busy = this._busy.has(d.name) || d.building;
    if (d.can_set_channel && (d.channel === "stable" || d.channel === "main" || !d.configuration)) {
      return `<select data-channel="${esc(d.name)}" ${busy ? "disabled" : ""} aria-label="Channel of ${esc(d.title)}">
        ${["stable", "main"]
          .map(
            (c) =>
              `<option value="${c}" ${d.channel === c ? "selected" : ""}>${CHANNEL_LABELS[c]}</option>`,
          )
          .join("")}
      </select>`;
    }
    if (!d.channel) return `<span class="muted">—</span>`;
    const label = CHANNEL_LABELS[d.channel] || d.channel;
    const ref = d.channel === "pinned" && d.ref ? ` <span class="muted">${esc(d.ref)}</span>` : "";
    const why = d.config_kind === "custom" ? ` title="Set by ref: in your own config"` : "";
    return `<span${why}>${esc(label)}</span>${ref}`;
  }

  _filter(d) {
    if (d.filter_life == null) return `<span class="muted">—</span>`;
    const value = Math.max(0, Math.min(100, d.filter_life));
    const level = value < 10 ? "bad" : value < 25 ? "low" : "good";
    return `<span class="filter ${level}"><span class="bar"><span style="width:${value}%"></span></span>${Math.round(
      d.filter_life,
    )} %</span>`;
  }

  _esphome(d) {
    if (!d.esphome_deployed && !d.esphome_current) return `<span class="muted">—</span>`;
    if (d.esphome_current && d.esphome_deployed && d.esphome_current !== d.esphome_deployed)
      return `${esc(d.esphome_deployed)}<div class="sub" title="The Device Builder runs a newer ESPHome; the next compile and upload brings it">builder ${esc(
        d.esphome_current,
      )}</div>`;
    return esc(d.esphome_deployed || d.esphome_current);
  }

  _actions(d) {
    if (!d.configuration)
      return `<button class="btn" data-action="navigate" data-path="${INTEGRATION_PAGE}" title="Add device → Device already in Home Assistant">Add config</button>`;
    const busy = this._busy.has(d.name) || d.building;
    const dis = busy ? "disabled" : "";
    return `<button class="btn" data-action="compile" data-name="${esc(d.name)}" ${dis}>Compile</button>
      <button class="btn ${d.update_available ? "primary" : ""}" data-action="upload" data-name="${esc(d.name)}" ${dis}>${
        d.update_available ? "Update" : "Compile &amp; upload"
      }</button>`;
  }

  _row(d) {
    // the name opens the device page (settings); the HA device page is linked there
    const pagePath = this._devicePath(d.name);
    const deviceLink = d.device_id
      ? `<a href="${esc(pagePath)}" data-action="navigate" data-path="${esc(pagePath)}" title="Settings of ${esc(d.title)}">${esc(d.title)}</a>`
      : esc(d.title);
    const latest = d.latest
      ? d.latest_url
        ? `<a href="${esc(d.latest_url)}" target="_blank" rel="noreferrer">${esc(d.latest)}</a>`
        : esc(d.latest)
      : `<span class="muted">—</span>`;
    return `<tr class="${d.update_available ? "has-update" : ""}">
      <td class="device" data-label="Device">
        <div class="name">${deviceLink}</div>
        <div class="sub">${esc(d.configuration || d.name)}</div>
      </td>
      <td data-label="Model">${d.model ? esc(d.model) : `<span class="muted">—</span>`}</td>
      <td data-label="ESP / config">${
        d.config_kind
          ? esc(KIND_LABELS[d.config_kind] || d.config_kind)
          : `<span class="muted">${d.configuration ? "…" : "—"}</span>`
      }</td>
      <td data-label="Channel">${this._channel(d)}</td>
      <td data-label="Installed" class="mono">${
        d.installed ? esc(d.installed) : `<span class="muted">—</span>`
      }</td>
      <td data-label="Latest" class="mono">${latest}</td>
      <td data-label="Filter">${this._filter(d)}</td>
      <td data-label="ESPHome" class="mono">${this._esphome(d)}</td>
      <td data-label="Status">${this._status(d)}${this._lastBuild(d)}</td>
      <td class="actions">${this._actions(d)}</td>
    </tr>`;
  }

  _summary() {
    const heads = this._data?.heads || {};
    const head = (channel) =>
      heads[channel]
        ? `<span><span class="muted">${CHANNEL_LABELS[channel]}</span> <a class="mono" href="${esc(
            heads[channel].url,
          )}" target="_blank" rel="noreferrer">${esc(heads[channel].version)}</a></span>`
        : "";
    const parts = [head("stable"), head("main")].filter(Boolean);
    if (this._data?.checked_at)
      parts.push(`<span class="muted">checked ${esc(this._time(this._data.checked_at))}</span>`);
    if (this._data && !this._data.last_update_success)
      parts.push(`<span class="bad">Device Builder not reachable</span>`);
    return parts.join(`<span class="dot">·</span>`);
  }

  _body() {
    if (this._error)
      return `<div class="card empty"><p class="bad">${esc(this._error)}</p>
        <p class="muted">Is Levoit ESPHome set up and loaded?</p>
        <button class="btn" data-action="retry">Try again</button></div>`;
    if (!this._data) return `<div class="card empty"><span class="spinner"></span> Loading…</div>`;
    const devices = this._data.devices;
    const pending = this._data.pending || [];
    if (!devices.length && !pending.length)
      return `<div class="card empty">
        <div class="big-icon">${icon("purifier")}</div>
        <p>No Levoit or Philips ESPHome device found yet.</p>
        <p class="muted">A device shows up when its Device Builder config loads the levoit or philips component, or when it reports the esp_version or model text sensor.</p>
        <button class="btn primary" data-action="navigate" data-path="${INTEGRATION_PAGE}">Add device</button>
      </div>`;
    const updates = devices.filter((d) => d.update_available).length;
    return `<div class="card">
      <div class="card-head">
        <span>${devices.length} device${devices.length === 1 ? "" : "s"}${
          updates ? ` · <span class="warn-text">${updates} with an update</span>` : ""
        }${pending.length ? ` · ${pending.length} not flashed yet` : ""}</span>
      </div>
      <table>
        <thead><tr>
          <th>Device</th><th>Model</th><th>ESP / config</th><th>Channel</th>
          <th>Installed</th><th>Latest</th><th>Filter</th><th>ESPHome</th><th>Status</th><th></th>
        </tr></thead>
        <tbody>${devices.map((d) => this._row(d)).join("")}${pending
          .map((p) => this._pendingRow(p))
          .join("")}</tbody>
      </table>
    </div>`;
  }

  // A config made by Add device whose ESP has not connected yet: flash it once
  // over USB from the Device Builder, then it becomes a normal device row.
  _pendingRow(p) {
    const busy = this._busy.has(p.name) || p.building;
    const builderUrl = this._data?.builder_url;
    const status = p.building
      ? `<span class="chip info"><span class="spinner"></span>${
          BUILD_STEP_LABELS[p.build_step] || "Building…"
        }</span>`
      : `<span class="chip info">Not flashed yet</span>`;
    const none = `<span class="muted">—</span>`;
    return `<tr class="pending">
      <td class="device" data-label="Device">
        <div class="name">${esc(p.title)}</div>
        <div class="sub">${esc(p.configuration)}</div>
      </td>
      <td data-label="Model">${p.model ? esc(p.model) : none}</td>
      <td data-label="ESP / config">${
        p.config_kind ? esc(KIND_LABELS[p.config_kind] || p.config_kind) : none
      }</td>
      <td data-label="Channel">${none}</td>
      <td data-label="Installed"><span class="muted">not flashed</span></td>
      <td data-label="Latest">${none}</td>
      <td data-label="Filter">${none}</td>
      <td data-label="ESPHome">${none}</td>
      <td data-label="Status">${status}${this._lastBuild(p)}
        <div class="sub hint">Device Builder: open ${esc(p.configuration)}, Install, Plug into this computer</div>
      </td>
      <td class="actions">
        <button class="btn" data-action="compile" data-name="${esc(p.name)}" ${busy ? "disabled" : ""} title="Check that the config builds, before flashing">Compile</button>${
          builderUrl
            ? `<button class="btn primary" data-action="navigate" data-path="${esc(builderUrl)}" title="Flash it there over USB: Install, Plug into this computer">Open Device Builder</button>`
            : ""
        }
      </td>
    </tr>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    // do not pull an open dropdown or a slider being dragged away from under the pointer
    // (or the history chart someone steps through with the arrow keys)
    const active = this.shadowRoot.activeElement?.tagName;
    if (
      active === "SELECT" ||
      active === "INPUT" ||
      this.shadowRoot.activeElement?.classList?.contains("hist")
    ) {
      this._deferred = true;
      return;
    }
    const showMenu = this._narrow || this._hass?.dockedSidebar === "always_hidden";
    const builderUrl = this._data?.builder_url;
    const version = this._panel?.config?.version;
    const onPage = this._view === "device" && Boolean(this._pageName);
    const onConfig = this._view === "config";
    const pageTitle =
      this._page?.title || this._device(this._pageName)?.title || this._pageName || "";
    const tabs = onPage
      ? ""
      : `<div class="tabs" role="tablist">
          <button class="tab${onConfig ? "" : " on"}" role="tab" aria-selected="${!onConfig}" data-action="navigate" data-path="${esc(this._base)}">Devices</button>
          <button class="tab${onConfig ? " on" : ""}" role="tab" aria-selected="${onConfig}" data-action="navigate" data-path="${esc(this._base)}/config">Updates &amp; config${
            (this._data?.devices || []).some((d) => d.update_available) ? `<span class="tab-dot" title="Updates available"></span>` : ""
          }</button>
        </div>`;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar">
        ${
          showMenu
            ? `<button class="icon-btn" data-action="menu" aria-label="Menu">${icon("menu")}</button>`
            : ""
        }${
          onPage
            ? `<button class="icon-btn back" data-action="navigate" data-path="${esc(this._base)}" aria-label="All devices" title="All devices">${icon("back")}</button>`
            : ""
        }
        <div class="title">${onPage ? esc(pageTitle) : "Levoit ESPHome"}</div>
        ${
          onConfig
            ? `<button class="icon-btn" data-action="check" ${this._checking ? "disabled" : ""} title="Check for new versions now" aria-label="Check for new versions now">${
                this._checking ? `<span class="spinner light"></span>` : icon("refresh")
              }</button>`
            : ""
        }
        ${
          builderUrl && onConfig
            ? `<button class="tb-btn" data-action="navigate" data-path="${esc(builderUrl)}" title="Open the ESPHome Device Builder">${icon(
                "builder",
              )}<span>Device Builder</span></button>`
            : ""
        }
        <button class="tb-btn" data-action="navigate" data-path="${INTEGRATION_PAGE}" title="Add device (on the integration page)">${icon(
          "plus",
        )}<span>Add device</span></button>
      </div>
      <div class="content">
        ${
          version && LOADED_VERSION && version !== LOADED_VERSION
            ? `<div class="notice">Levoit ESPHome was updated to ${esc(version)}; this page still runs ${esc(
                LOADED_VERSION,
              )}. <button class="btn primary" data-action="reload">Reload this page</button></div>`
            : ""
        }
        ${tabs}
        ${
          onPage
            ? this._devicePage()
            : onConfig
              ? `<div class="summary">${this._summary()}</div>${this._body()}`
              : this._overview()
        }
        <div class="footer muted">Levoit ESPHome${version ? ` ${esc(version)}` : ""}${
          onConfig ? " · builds run in the ESPHome Device Builder; the last build's output is under Log" : ""
        }</div>
      </div>
      ${this._logDialog()}`;
    const pre = this.shadowRoot.querySelector(".log pre");
    if (pre) pre.scrollTop = pre.scrollHeight; // newest lines in view
    if (this._hass) {
      this._seen = {};
      for (const entityId of this._watched()) this._seen[entityId] = this._hass.states[entityId];
    }
    this._bindHistory();
  }

  // --- overview: every device as a card, for using them --------------------------

  _overview() {
    const devices = this._data?.devices || [];
    const pending = this._data?.pending || [];
    // loading, errors and no devices at all: as on the config tab
    if (this._error || !this._data || (!devices.length && !pending.length)) return this._body();
    const cards = devices.map((d) => this._deviceCard(d)).join("");
    const waiting = pending.length
      ? `<div class="muted overview-note">${pending.length} device${pending.length === 1 ? "" : "s"} not flashed yet: see <a href="${esc(
          this._base,
        )}/config" data-action="navigate" data-path="${esc(this._base)}/config">Updates &amp; config</a></div>`
      : "";
    return `<div class="overview">${cards}</div>${waiting}`;
  }

  // a device's state for a controls key, from the subscription's mapping
  _dstate(d, key) {
    const entityId = d.controls?.[key];
    return entityId ? this._hass?.states?.[entityId] || null : null;
  }

  _deviceCard(d) {
    const fan = this._dstate(d, "fan.fan");
    const usable = this._usable(fan);
    const on = fan?.state === "on";
    const a = fan?.attributes || {};
    const step = Number(a.percentage_step) || 25;
    const count = Math.max(1, Math.round(100 / step));
    const level = on ? Math.round((Number(a.percentage) || 0) / step) : 0;
    const offline = d.online === false || (fan && !usable && fan.state !== "off");
    // status line: only what the buttons do not show
    const mode = !fan ? "" : offline ? "Offline" : on ? "" : "Off";
    // mode and speed, as on the device page (small); a click turns it on too
    const dis = offline ? "disabled" : "";
    const modeButtons = (a.preset_modes || [])
      .map(
        (m) =>
          `<button class="seg sm${on && m === a.preset_mode ? " on" : ""}" ${dis} ${this._svc("fan", "set_preset_mode", fan.entity_id, {
            preset_mode: m,
          })}>${esc(m)}</button>`,
      )
      .join("");
    const speedButtons = fan
      ? Array.from({ length: count }, (_, i) => i + 1)
          .map(
            (n) =>
              `<button class="seg sm${n === level ? " on" : ""}" aria-label="Speed ${n}" ${dis} ${this._svc(
                "fan",
                "set_percentage",
                fan.entity_id,
                { percentage: Math.min(100, Math.floor(n * step)) },
              )}>${d.model === "ELEVA300X" && n === count ? "Turbo" : n}</button>`,
          )
          .join("")
      : "";
    const controls =
      fan && !offline && (modeButtons || speedButtons)
        ? `<div class="dc-controls">${modeButtons ? `<div class="segs">${modeButtons}</div>` : ""}${
            speedButtons ? `<div class="segs">${speedButtons}</div>` : ""
          }</div>`
        : "";
    const timerLeft =
      parseDuration(this._dstate(d, "text_sensor.timer_duration_remaining")?.state) / 60;
    const stat = (key, label) => {
      const st = this._dstate(d, key);
      if (!st) return "";
      const value = this._usable(st) ? formatNumber(parseFloat(st.state)) : "—";
      const unit = this._usable(st) ? st.attributes.unit_of_measurement || "" : "";
      // the unit goes with the label, so the number always fits the tile
      return `<div class="dc-stat"><div class="dc-val">${esc(value)}</div><div class="dc-label">${esc(label)}${
        unit ? ` · ${esc(unit)}` : ""
      }</div></div>`;
    };
    const aqiKey = d.controls?.["sensor.aqi_index"] ? "sensor.aqi_index" : "sensor.aqi";
    const stats = [stat("sensor.pm25", "PM2.5"), stat(aqiKey, "AQI"), stat("sensor.current_cadr", "CADR")].join("");
    const power = fan
      ? `<button class="power small${on ? " on" : ""}" aria-label="${on ? `Turn ${esc(d.title)} off` : `Turn ${esc(d.title)} on`}" title="${
          on ? "Turn off" : "Turn on"
        }" ${offline ? "disabled" : ""} ${this._svc("fan", on ? "turn_off" : "turn_on", fan.entity_id)}>${icon("power")}</button>`
      : "";
    const path = this._devicePath(d.name);
    return `<div class="dcard${on ? " on" : ""}${offline ? " offline" : ""}" role="link" tabindex="0" data-action="navigate" data-path="${esc(
      path,
    )}" aria-label="${esc(d.title)}: open its page">
      <div class="dc-top">
        ${deviceImage(d.model)}
        <div class="dc-name">
          <div class="name">${esc(d.title)}</div>
          <div class="sub">${esc(d.model || "Levoit")}</div>
        </div>
        ${power}
      </div>
      ${controls}
      ${
        mode || d.update_available || (timerLeft > 0 && on)
          ? `<div class="dc-mode"><span>${esc(mode)}</span>${
              timerLeft > 0 && on ? `<span class="chip info">Off in ${esc(formatMinutes(timerLeft))}</span>` : ""
            }${
              d.update_available
                ? `<button class="chip warning chip-btn" data-action="navigate" data-path="${esc(this._base)}/config" title="Open Updates &amp; config">Update</button>`
                : ""
            }</div>`
          : ""
      }
      ${stats ? `<div class="dc-stats">${stats}</div>` : ""}
    </div>`;
  }

  // --- device page: control helpers -------------------------------------------
  // Each takes a controls key ("select.auto_mode", ...) and renders nothing when
  // the device has no such entity, so a section shows what the model has.

  _state(key) {
    const entityId = this._page?.controls?.[key];
    return entityId ? this._hass?.states?.[entityId] || null : null;
  }

  _usable(st) {
    return Boolean(st) && st.state !== "unavailable" && st.state !== "unknown";
  }

  _number(key) {
    const st = this._state(key);
    const value = st ? parseFloat(st.state) : NaN;
    return Number.isNaN(value) ? null : value;
  }

  // attributes for a button that calls a service on one entity
  _svc(domain, service, entityId, args, confirmText) {
    return `data-action="svc" data-domain="${domain}" data-service="${service}" data-entity="${esc(
      entityId,
    )}" data-args="${esc(JSON.stringify(args || {}))}"${
      confirmText ? ` data-confirm="${esc(confirmText)}"` : ""
    }`;
  }

  _setting(label, hint, control, dim) {
    return `<div class="setting${dim ? " dim" : ""}">
      <div class="s-label">${esc(label)}${hint ? `<div class="hint">${esc(hint)}</div>` : ""}</div>
      <div class="s-control">${control}</div>
    </div>`;
  }

  _toggle(key, label, hint, { dim = false } = {}) {
    const st = this._state(key);
    if (!st) return "";
    const on = st.state === "on";
    const off = !this._usable(st) || dim;
    return this._setting(
      label,
      hint,
      `<button class="switch${on ? " on" : ""}" role="switch" aria-checked="${on}" aria-label="${esc(
        label,
      )}" ${off ? "disabled" : ""} ${this._svc("switch", on ? "turn_off" : "turn_on", st.entity_id)}><span></span></button>`,
      dim,
    );
  }

  _choices(key, label, hint, { dim = false, labels = {} } = {}) {
    const st = this._state(key);
    if (!st) return "";
    const off = !this._usable(st) || dim;
    const buttons = (st.attributes.options || [])
      .map(
        (option) =>
          `<button class="seg${option === st.state ? " on" : ""}" ${off ? "disabled" : ""} ${this._svc(
            "select",
            "select_option",
            st.entity_id,
            { option },
          )}>${esc(labels[option] || option)}</button>`,
      )
      .join("");
    return this._setting(label, hint, `<div class="segs">${buttons}</div>`, dim);
  }

  // `also`: a second number entity set to the same value (see the room size)
  _slider(key, label, hint, { dim = false, unit, also } = {}) {
    const st = this._state(key);
    if (!st) return "";
    const alsoEntity = also ? this._page?.controls?.[also] : null;
    const a = st.attributes;
    const value = parseFloat(st.state);
    const known = !Number.isNaN(value);
    const off = !this._usable(st) || dim;
    const shown = known ? `${formatNumber(value)}${(unit ?? a.unit_of_measurement) ? ` ${unit ?? a.unit_of_measurement}` : ""}` : "—";
    return this._setting(
      label,
      hint,
      `<div class="slider"><input type="range" min="${esc(a.min)}" max="${esc(a.max)}" step="${esc(
        a.step || 1,
      )}" value="${esc(known ? value : a.min)}" data-number="${esc(st.entity_id)}"${
        alsoEntity ? ` data-also="${esc(alsoEntity)}"` : ""
      } aria-label="${esc(
        label,
      )}" ${off ? "disabled" : ""}><span class="val">${esc(shown)}</span></div>`,
      dim,
    );
  }

  _stepper(key, label, hint, { dim = false, format } = {}) {
    const st = this._state(key);
    if (!st) return "";
    const a = st.attributes;
    const value = parseFloat(st.state);
    const known = !Number.isNaN(value);
    const off = !this._usable(st) || dim || !known;
    const step = Number(a.step) || 1;
    const show = format || ((v) => `${formatNumber(v)}${a.unit_of_measurement ? ` ${a.unit_of_measurement}` : ""}`);
    const button = (delta, text) => {
      const next = Math.min(Number(a.max), Math.max(Number(a.min), value + delta));
      return `<button class="step" aria-label="${delta < 0 ? "Less" : "More"}" ${
        off || next === value ? "disabled" : ""
      } ${this._svc("number", "set_value", st.entity_id, { value: next })}>${text}</button>`;
    };
    return this._setting(
      label,
      hint,
      `<div class="stepper">${button(-step, "−")}<span class="val">${
        known ? esc(show(value)) : "—"
      }</span>${button(step, "+")}</div>`,
      dim,
    );
  }

  _readout(key, label, { unit, format } = {}) {
    const st = this._state(key);
    if (!st) return "";
    const value = this._usable(st)
      ? format
        ? format(st.state)
        : `${st.state}${(unit ?? st.attributes.unit_of_measurement) ? ` ${unit ?? st.attributes.unit_of_measurement}` : ""}`
      : "—";
    return this._setting(label, "", `<span class="readout">${esc(value)}</span>`);
  }

  _tile(key, label) {
    const st = this._state(key);
    if (!st) return "";
    const value = this._usable(st) ? st.state : "—";
    const unit = this._usable(st) ? st.attributes.unit_of_measurement || "" : "";
    return `<div class="tile"><div class="t-val">${esc(value)}${
      unit ? `<span class="unit">${esc(unit)}</span>` : ""
    }</div><div class="t-label">${esc(label)}</div></div>`;
  }

  _section(title, rows, hint) {
    const body = rows.filter(Boolean).join("");
    if (!body) return "";
    return `<div class="card section">
      <div class="sec-head">${esc(title)}${hint ? `<div class="hint">${esc(hint)}</div>` : ""}</div>
      ${body}
    </div>`;
  }

  _subhead(text) {
    return `<div class="subhead">${esc(text)}</div>`;
  }

  // --- device page: sections ---------------------------------------------------

  _devicePage() {
    if (this._pageError)
      return `<div class="card empty"><p class="bad">${esc(this._pageError)}</p>
        <button class="btn" data-action="page-retry">Try again</button></div>`;
    const page = this._page;
    if (!page) return `<div class="card empty"><span class="spinner"></span> Loading…</div>`;
    const haDevice = `/config/devices/device/${page.device_id}`;
    const haLink = `<button class="btn" data-action="navigate" data-path="${esc(haDevice)}">${icon(
      "open",
    )}<span>Home Assistant device page</span></button>`;
    if (!page.supported)
      return `<div class="card empty">
        <div class="big-icon">${icon("purifier")}</div>
        <p>${page.model ? `The ${esc(page.model)}` : "This device"} has no settings page here yet.</p>
        <p class="muted">Its settings are on the Home Assistant device page.</p>
        ${haLink}
      </div>`;
    const settings = Object.keys(page.controls).filter((key) => !key.startsWith("text_sensor."));
    if (!settings.length)
      return `<div class="card empty">
        <p>No settings of this device found.</p>
        <p class="muted">They are found by entity name, as the tuct/levoit configs name them${
          page.from_config ? " or as its config does" : ""
        }. Renamed entities are on the Home Assistant device page.</p>
        ${haLink}
      </div>`;
    return `<div class="page-head">
        <span class="chip">${esc(page.model || "Levoit")}</span>
        ${this._onlineChip()}
        <span class="spacer"></span>
        ${haLink}
      </div>
      ${this._alerts()}
      ${this._hero()}
      ${this._historyCard()}
      <div class="sections">
        ${this._autoSection()}
        ${this._sleepSection()}
        ${this._quietSection()}
        ${this._timerSection()}
        ${this._displaySection()}
        ${this._filterSection()}
        ${this._infoSection()}
      </div>`;
  }

  _onlineChip() {
    const fan = this._state("fan.fan");
    if (!fan) return "";
    return this._usable(fan) || fan.state === "off"
      ? `<span class="chip success">Online</span>`
      : `<span class="chip warning">Offline</span>`;
  }

  _alerts() {
    const alerts = [];
    if (this._state("binary_sensor.cover_open")?.state === "on")
      alerts.push("The cover is open: the purifier stays off until it is closed.");
    const error = this._state("text_sensor.error_message");
    if (this._usable(error) && !/^ok$/i.test(error.state)) alerts.push(`Error: ${error.state}`);
    if (this._state("binary_sensor.filter_low")?.state === "on")
      alerts.push("The filter is nearly used up: time for a new one.");
    return alerts.map((text) => `<div class="notice warn">${esc(text)}</div>`).join("");
  }

  _hero() {
    const fan = this._state("fan.fan");
    const tiles = [
      this._tile("sensor.pm25", "PM2.5"),
      this._tile("sensor.pm1_0", "PM1.0"),
      this._tile("sensor.pm10", "PM10"),
      this._tile("sensor.aqi_index", "AQI"),
      this._tile("sensor.aqi", this._state("sensor.aqi_index") ? "Air quality level" : "AQI"),
      this._tile("sensor.current_cadr", "CADR now"),
    ].join("");
    let controls = "";
    if (fan) {
      const usable = this._usable(fan);
      const on = fan.state === "on";
      const a = fan.attributes;
      const step = Number(a.percentage_step) || 25;
      const count = Math.max(1, Math.round(100 / step));
      const level = on ? Math.round((Number(a.percentage) || 0) / step) : 0;
      const turbo = this._page.model === "ELEVA300X";
      const speeds = Array.from({ length: count }, (_, i) => i + 1)
        .map(
          (n) =>
            `<button class="seg${n === level ? " on" : ""}" ${usable ? "" : "disabled"} ${this._svc(
              "fan",
              "set_percentage",
              fan.entity_id,
              // floor: 2 of 3 speeds is 66 %, which Home Assistant maps to speed 2 (67 % would be 3)
              { percentage: Math.min(100, Math.floor(n * step)) },
            )}>${turbo && n === count ? "Turbo" : n}</button>`,
        )
        .join("");
      const presets = (a.preset_modes || [])
        .map(
          (mode) =>
            `<button class="seg${on && mode === a.preset_mode ? " on" : ""}" ${usable ? "" : "disabled"} ${this._svc(
              "fan",
              "set_preset_mode",
              fan.entity_id,
              { preset_mode: mode },
            )}>${esc(mode)}</button>`,
        )
        .join("");
      controls = `<div class="hero-controls">
        <button class="power${on ? " on" : ""}" aria-label="${on ? "Turn off" : "Turn on"}" title="${
          on ? "Turn off" : "Turn on"
        }" ${usable || fan.state === "off" ? "" : "disabled"} ${this._svc(
          "fan",
          on ? "turn_off" : "turn_on",
          fan.entity_id,
        )}>${icon("power")}</button>
        <div class="hero-rows">
          ${presets ? `<div class="hero-row"><span class="h-label">Mode</span><div class="segs">${presets}</div></div>` : ""}
          <div class="hero-row"><span class="h-label">Speed</span><div class="segs">${speeds}</div></div>
        </div>
      </div>`;
    }
    const vent = this._slider("number.vent_angle", "Vent angle", "45° points up, 90° straight ahead");
    return `<div class="card hero">
      ${controls}
      ${tiles ? `<div class="tiles">${tiles}</div>` : ""}
      ${vent}
    </div>`;
  }

  _autoSection() {
    const mode = this._state("select.auto_mode");
    const roomSize = mode && /room|effic/i.test(mode.state);
    const highFan = this._state("text_sensor.auto_mode_room_size_high_fan");
    const highFanLeft = this._usable(highFan) && parseDuration(highFan.state) > 0;
    return this._section(
      "Automatic",
      [
        this._choices("select.auto_mode", "Auto mode", "How Auto picks the speed. Choosing one switches the fan to Auto"),
        // The preset number is only remembered on the ESP (sent when Room
        // Size is picked); the room size number sends it to the purifier now.
        // Set both, so a change applies at once and survives a mode change.
        roomSize
          ? this._state("number.auto_profile_room_size_input")
            ? this._slider("number.auto_profile_room_size_input", "Room size", "Auto runs for a room this size", {
                also: "number.efficiency_room_size",
              })
            : this._slider("number.efficiency_room_size", "Room size", "Auto runs for a room this size")
          : "",
        highFanLeft ? this._readout("text_sensor.auto_mode_room_size_high_fan", "High speed for another") : "",
        this._toggle("switch.dynamic_manual", "Dynamic manual", "In Manual, the speed goes up when the air gets bad"),
        this._toggle("switch.adaptive_start", "Adaptive start", "Stored on the purifier; VeSync runs it in its cloud"),
      ],
    );
  }

  // Vital 200S: a custom sleep profile runs quick clean, then sleep, then the
  // daytime mode. On the Default profile the purifier ignores these settings.
  _sleepSection() {
    const profile = this._state("select.sleep_preference");
    if (!profile) return "";
    const dim = profile.state === "Default";
    const sleepLevel = (v) => (v >= 5 ? "Auto" : `Level ${formatNumber(v)}`);
    return this._section(
      "Sleep",
      [
        this._choices("select.sleep_preference", "Sleep profile", "Custom1 / Custom2 use the steps below; Default uses the purifier's own"),
        dim ? `<div class="hint pad">Pick Custom1 or Custom2 to change the steps below.</div>` : "",
        this._subhead("1 · Quick clean first"),
        this._toggle("switch.quick_clean", "Quick clean", "Run fast for a while before sleep", { dim }),
        this._stepper("number.quick_clean_minutes", "For", "", { dim, format: (v) => formatMinutes(v) }),
        this._stepper("number.quick_clean_fan_level", "At level", "", { dim, format: (v) => `Level ${formatNumber(v)}` }),
        this._subhead("2 · Sleep"),
        this._stepper("number.sleep_minutes", "Sleep for", "", { dim, format: (v) => formatMinutes(v) }),
        this._stepper("number.sleep_fan_level", "At level", "", { dim, format: sleepLevel }),
        this._subhead("3 · Then"),
        this._toggle("switch.daytime_enabled", "Daytime mode", "Switch to a daytime mode when sleep ends", { dim }),
        this._choices("select.daytime_fan_mode", "Mode", "", { dim }),
        this._stepper("number.daytime_fan_level", "Level", "", { dim, format: (v) => `Level ${formatNumber(v)}` }),
      ],
    );
  }

  // Eleva 300X: the purifier lowers the fan one level during its quiet period
  _quietSection() {
    if (!this._state("switch.quiet_period") && !this._state("switch.dynamic_sleep")) return "";
    const trigger = this._state("select.quiet_trigger");
    const byTime = trigger?.state === "Timer";
    const active = this._state("binary_sensor.quiet_active")?.state === "on";
    const start = this._state("number.quiet_start");
    const end = this._state("number.quiet_end");
    const time = (st) =>
      st
        ? `<input type="time" step="1800" value="${esc(
            this._usable(st) ? hoursToTime(parseFloat(st.state)) : "",
          )}" data-number="${esc(st.entity_id)}" ${this._usable(st) ? "" : "disabled"}>`
        : "";
    return this._section(
      "Quiet period",
      [
        this._toggle(
          "switch.quiet_period",
          "Quiet period",
          active ? "Active now: the fan runs one level lower" : "Runs the fan one level lower",
        ),
        this._choices("select.quiet_trigger", "Starts", "", { labels: { Light: "When dark", Timer: "At set times" } }),
        byTime && (start || end)
          ? this._setting("From – to", "", `<div class="times">${time(start)}<span>–</span>${time(end)}</div>`)
          : "",
        this._toggle("switch.dynamic_sleep", "Dynamic sleep", "In Sleep, the speed goes up when the air gets bad"),
      ],
    );
  }

  _timerSection() {
    const timer = this._state("number.timer");
    if (!timer) return "";
    const left = parseDuration(this._state("text_sensor.timer_duration_remaining")?.state) / 60;
    const total = parseDuration(this._state("text_sensor.timer_duration_initial")?.state) / 60;
    const running = left > 0;
    const max = Number(timer.attributes.max) || 1440;
    const usable = this._usable(timer);
    const presets = [30, 60, 120, 240, 480, 720].filter((m) => m <= max);
    const set = (minutes, text) =>
      `<button class="seg" ${usable ? "" : "disabled"} ${this._svc("number", "set_value", timer.entity_id, {
        value: minutes,
      })}>${esc(text)}</button>`;
    const status = running
      ? `<div class="timer-run">
          <div class="big">${esc(formatMinutes(left))} <span class="muted">left${
            total ? ` of ${esc(formatMinutes(total))}` : ""
          }</span></div>
          ${total ? `<div class="bar"><span style="width:${Math.min(100, Math.round((left / total) * 100))}%"></span></div>` : ""}
        </div>`
      : `<div class="muted pad">No timer running</div>`;
    return this._section(
      "Timer",
      [
        status,
        this._setting(
          running ? "New timer" : "Turn off in",
          "",
          `<div class="segs">${presets.map((m) => set(m, formatMinutes(m))).join("")}${
            running ? set(0, "Cancel") : ""
          }</div>`,
        ),
      ],
      "The purifier turns off when the timer ends",
    );
  }

  _displaySection() {
    const dark = this._state("binary_sensor.dark_detected");
    const lightHint = `Dims the display in the dark${
      dark && this._usable(dark) ? ` (now: ${dark.state === "on" ? "dark" : "light"})` : ""
    }`;
    return this._section("Display & panel", [
      this._toggle("switch.display", "Display", "The panel's lights"),
      this._toggle("switch.light_detect", "Light detect", lightHint),
      this._choices("select.nightlight", "Night light", ""),
      this._toggle("switch.aqi_ring_dim", "Dim the AQI ring", ""),
      this._toggle("switch.mute", "Mute", "No beeps from the panel"),
      this._toggle("switch.child_lock", "Child lock", "The buttons on the purifier do nothing"),
    ]);
  }

  _filterSection() {
    const life = this._number("sensor.filter_life_left");
    const reset = this._state("button.reset_filter_stats");
    const bar =
      life === null
        ? ""
        : `<div class="filter-big${life < 5 ? " bad" : life < 20 ? " low" : ""}">
            <div class="big">${esc(formatNumber(life))} %</div>
            <div class="bar"><span style="width:${Math.max(0, Math.min(100, life))}%"></span></div>
          </div>`;
    return this._section(
      "Filter",
      [
        bar,
        this._stepper("number.filter_lifetime_months", "Lasts", "Expected filter life, used for the %", {
          format: (v) => `${formatNumber(v)} month${v === 1 ? "" : "s"}`,
        }),
        reset
          ? this._setting(
              "New filter fitted",
              "Starts the filter life at 100 % again",
              `<button class="btn" ${this._usable(reset) || reset.state === "unknown" ? "" : "disabled"} ${this._svc(
                "button",
                "press",
                reset.entity_id,
                {},
                "Reset the filter life to 100 %? Do this after fitting a new filter.",
              )}>Reset</button>`,
            )
          : "",
      ],
      "Worked out on the ESP from the air moved, not measured",
    );
  }

  // --- device page: history chart ----------------------------------------------

  // the air quality sensors this device has, one chart each
  _historySeries() {
    const controls = this._page?.controls || {};
    return HISTORY_SERIES.filter(
      (s) => controls[s.key] && !(s.key === "sensor.aqi" && controls["sensor.aqi_index"]),
    ).map((s) => ({ ...s, entity: controls[s.key] }));
  }

  async _loadHistory() {
    const series = this._historySeries();
    if (!series.length || !this._hass) return;
    const name = this._pageName;
    const rangeKey = this._historyRange;
    const range = HISTORY_RANGES[rangeKey];
    const end = Date.now();
    const start = end - range.ms;
    this._historyLoading = true;
    try {
      const result = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        statistic_ids: series.map((s) => s.entity),
        period: range.period,
        types: ["mean"],
      });
      if (name !== this._pageName || rangeKey !== this._historyRange) return;
      const data = {};
      for (const s of series)
        data[s.entity] = (result?.[s.entity] || [])
          .map((p) => [typeof p.start === "number" ? p.start : Date.parse(p.start), p.mean])
          .filter(([t, v]) => Number.isFinite(t) && v !== null && v !== undefined);
      this._history = { name, range: rangeKey, start, end, at: Date.now(), data };
      this._historyError = null;
    } catch (err) {
      if (name === this._pageName) this._historyError = err?.message || String(err);
    } finally {
      this._historyLoading = false;
      this._render();
    }
  }

  _historyCard() {
    const series = this._historySeries();
    if (!series.length) return "";
    const h = this._history;
    const ranges = Object.entries(HISTORY_RANGES)
      .map(
        ([key, r]) =>
          `<button class="seg${key === this._historyRange ? " on" : ""}" data-action="history-range" data-range="${key}">${esc(
            r.label,
          )}</button>`,
      )
      .join("");
    let body;
    if (this._historyError && !h)
      body = `<div class="muted pad">History not available: ${esc(this._historyError)}</div>`;
    else if (!h) body = `<div class="muted pad"><span class="spinner"></span> Loading…</div>`;
    else {
      const stale = this._historyLoading || h.range !== this._historyRange;
      body = `<div class="hist${stale ? " stale" : ""}" tabindex="0" aria-label="Air quality history, ${esc(
        HISTORY_RANGES[h.range].label,
      )}; arrow keys move through the readings">
        ${series.map((s) => this._chartPanel(s, h)).join("")}
        ${this._timeAxis(h)}
        <div class="hist-tip" hidden></div>
      </div>`;
    }
    return `<div class="card history">
      <div class="sec-head hist-head"><span>History</span><div class="segs">${ranges}</div></div>
      ${body}
    </div>`;
  }

  _x(t, h) {
    return ((t - h.start) / (h.end - h.start)) * CHART.width;
  }

  _chartPanel(s, h) {
    const { width, height, top, bottom } = CHART;
    const points = h.data[s.entity] || [];
    const st = this._hass?.states?.[s.entity];
    const unit = st?.attributes?.unit_of_measurement || "";
    const now = this._usable(st) ? `${formatNumber(parseFloat(st.state))}${unit ? ` ${unit}` : ""}` : "—";
    const head = `<div class="hist-title"><span>${esc(s.title)}</span><span class="hist-now">${esc(now)}</span></div>`;
    if (!points.length)
      return `${head}<div class="hist-empty muted">No history yet</div>`;
    const max = niceMax(Math.max(...points.map(([, v]) => v)));
    const y = (v) => top + (1 - v / max) * (height - top - bottom);
    const base = y(0);
    // a gap of more than two periods (device offline) breaks the line
    const gap = HISTORY_RANGES[h.range].step * 2.5;
    const runs = [];
    for (const p of points) {
      const run = runs[runs.length - 1];
      if (run && p[0] - run[run.length - 1][0] <= gap) run.push(p);
      else runs.push([p]);
    }
    const line = (run) => run.map(([t, v], i) => `${i ? "L" : "M"}${this._x(t, h).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const area = (run) =>
      `${line(run)}L${this._x(run[run.length - 1][0], h).toFixed(1)},${base}L${this._x(run[0][0], h).toFixed(1)},${base}Z`;
    const grid = [0, max / 2, max]
      .map((v) => `<line class="grid" x1="0" x2="${width}" y1="${y(v)}" y2="${y(v)}"></line>`)
      .join("");
    // y labels: 0 and the top, in the column left of the plot
    const ticks = [max, 0]
      .map(
        (v) =>
          `<span class="ytick" style="top:${((y(v) / height) * 100).toFixed(1)}%">${esc(formatNumber(v))}</span>`,
      )
      .join("");
    // a lone reading (between gaps) is a dot: a zero-length line with round caps
    const mark = (run) =>
      run.length > 1
        ? `<path class="line" d="${line(run)}"></path>`
        : `<path class="line dot" d="${line(run)}h0.01"></path>`;
    return `${head}<div class="hist-row"><div class="hist-y">${ticks}</div>
      <svg class="hist-plot" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${esc(
        `${s.title}, ${HISTORY_RANGES[h.range].label}, up to ${formatNumber(max)}${unit ? ` ${unit}` : ""}`,
      )}">
        ${grid}
        ${runs.map((run) => `<path class="area" d="${area(run)}"></path>`).join("")}
        ${runs.map(mark).join("")}
        <line class="xhair" y1="0" y2="${height}" x1="0" x2="0" visibility="hidden"></line>
      </svg></div>`;
  }

  // shared time axis under the charts: every 6 hours, or every day at midnight
  _timeAxis(h) {
    const lang = this._hass?.locale?.language;
    const ticks = [];
    const first = new Date(h.start);
    if (h.range === "day") {
      first.setMinutes(0, 0, 0);
      first.setHours(Math.ceil((first.getHours() + 1) / 6) * 6);
      for (let t = first.getTime(); t <= h.end; t += 6 * 3600e3)
        ticks.push([t, new Date(t).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })]);
    } else {
      first.setHours(24, 0, 0, 0);
      for (let t = first.getTime(); t <= h.end; t += 24 * 3600e3)
        ticks.push([t, new Date(t).toLocaleDateString(lang, { weekday: "short" })]);
    }
    return `<div class="hist-row"><div class="hist-y"></div><div class="hist-axis" aria-hidden="true">${ticks
      .map(
        ([t, text]) =>
          `<span class="xtick" style="left:${((this._x(t, h) / CHART.width) * 100).toFixed(2)}%">${esc(text)}</span>`,
      )
      .join("")}</div></div>`;
  }

  // the crosshair and tooltip are drawn into the rendered chart, not re-rendered
  _bindHistory() {
    const hist = this.shadowRoot?.querySelector?.(".hist");
    if (!hist || !this._history) return;
    const timeAt = (clientX) => {
      const rect = hist.querySelector(".hist-plot")?.getBoundingClientRect();
      if (!rect || !rect.width) return null;
      const h = this._history;
      return h.start + ((clientX - rect.left) / rect.width) * (h.end - h.start);
    };
    hist.addEventListener("pointermove", (ev) => this._showHover(timeAt(ev.clientX)));
    hist.addEventListener("pointerleave", () => this._showHover(null));
    hist.addEventListener("blur", () => this._showHover(null));
    hist.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      ev.preventDefault();
      const h = this._history;
      const step = HISTORY_RANGES[h.range].step * (ev.key === "ArrowLeft" ? -1 : 1);
      this._showHover(Math.min(h.end, Math.max(h.start, (this._hoverT ?? h.end) + step)));
    });
    if (this._hoverT !== null) this._showHover(this._hoverT);
  }

  _showHover(t) {
    const hist = this.shadowRoot?.querySelector?.(".hist");
    const h = this._history;
    if (!hist || !h) return;
    const tip = hist.querySelector(".hist-tip");
    const hairs = hist.querySelectorAll(".xhair");
    if (t === null || t < h.start || t > h.end) {
      this._hoverT = null;
      tip.hidden = true;
      hairs.forEach((line) => line.setAttribute("visibility", "hidden"));
      return;
    }
    // snap to the nearest reading of any series
    let snapped = null;
    for (const points of Object.values(h.data))
      for (const [pt] of points) if (snapped === null || Math.abs(pt - t) < Math.abs(snapped - t)) snapped = pt;
    if (snapped === null) return;
    this._hoverT = snapped;
    const x = this._x(snapped, h);
    hairs.forEach((line) => {
      line.setAttribute("x1", x);
      line.setAttribute("x2", x);
      line.setAttribute("visibility", "visible");
    });
    // values lead, names follow; text via textContent
    const lang = this._hass?.locale?.language;
    const when = new Date(snapped);
    tip.textContent = "";
    const time = document.createElement("div");
    time.className = "tip-time";
    time.textContent =
      h.range === "day"
        ? when.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })
        : when.toLocaleString(lang, { weekday: "short", hour: "2-digit", minute: "2-digit" });
    tip.appendChild(time);
    const tolerance = HISTORY_RANGES[h.range].step / 2;
    for (const s of this._historySeries()) {
      const hit = (h.data[s.entity] || []).find(([pt]) => Math.abs(pt - snapped) <= tolerance);
      const unit = this._hass?.states?.[s.entity]?.attributes?.unit_of_measurement || "";
      const row = document.createElement("div");
      row.className = "tip-row";
      const value = document.createElement("strong");
      value.textContent = hit ? `${formatNumber(Math.round(hit[1] * 10) / 10)}${unit ? ` ${unit}` : ""}` : "—";
      const label = document.createElement("span");
      label.textContent = s.title;
      row.append(value, label);
      tip.appendChild(row);
    }
    tip.hidden = false;
    // keep the tooltip inside the chart: left of the crosshair past the middle.
    // Positioned in the plot column (the y labels take the first 40px).
    const share = x / CHART.width;
    tip.style.left = share > 0.5 ? "" : `calc(40px + (100% - 40px) * ${share.toFixed(4)} + 12px)`;
    tip.style.right = share > 0.5 ? `calc((100% - 40px) * ${(1 - share).toFixed(4)} + 12px)` : "";
  }

  _infoSection() {
    const rows = [
      this._readout("text_sensor.model", "Model"),
      this._readout("text_sensor.esp_version", "Component"),
      this._readout("text_sensor.mcu_version", "MCU firmware"),
      this._readout("text_sensor.error_message", "Status"),
      this._readout("sensor.ambient_light", "Ambient light"),
    ].filter(Boolean);
    if (!rows.length) return "";
    // open state kept here: the page re-renders on every state change
    return `<details class="card section info" ${this._infoOpen ? "open" : ""}>
      <summary class="sec-head" data-action="toggle-info" aria-expanded="${Boolean(this._infoOpen)}">
        <span>Info</span>${icon("chevron")}
      </summary>
      ${rows.join("")}
      <div class="hint pad">Settings found by entity name${
        this._page.from_config ? ", as named in the device's config" : ", as the tuct/levoit configs name them"
      }.</div>
    </details>`;
  }

  // --- build log ----------------------------------------------------------------

  async _showLog(name) {
    const device = this._device(name);
    try {
      const result = await this._hass.callWS({ type: "levoit_esphome/build_log", name });
      this._log = { name, title: device ? device.title : name, ...result };
    } catch (err) {
      this._toast(`Log: ${err.message || err}`);
      return;
    }
    this._render();
  }

  _logDialog() {
    if (!this._log) return "";
    const { title, lines, building } = this._log;
    return `<div class="backdrop" data-action="close-log">
      <div class="log" role="dialog" aria-label="Build log of ${esc(title)}">
        <div class="log-head">
          <span>${esc(title)}: ${building ? "running build" : "last build"}</span>
          <button class="btn" data-action="log" data-name="${esc(this._log.name)}">Refresh</button>
          <button class="btn" data-action="close-log">Close</button>
        </div>
        <pre>${lines.length ? lines.map(esc).join("\n") : "No output yet."}</pre>
      </div>
    </div>`;
  }
}

const STYLE = `
:host {
  display: block;
  min-height: 100vh;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, sans-serif));
  -webkit-font-smoothing: antialiased;
}
a { color: var(--primary-color); text-decoration: none; }
a:hover { text-decoration: underline; }
svg { width: 24px; height: 24px; fill: currentColor; flex: none; }
.muted { color: var(--secondary-text-color); }
.bad { color: var(--error-color, #db4437); }
.warn-text { color: var(--warning-color, #ffa600); }
.mono { font-variant-numeric: tabular-nums; }

.toolbar {
  display: flex; align-items: center; gap: 4px;
  height: var(--header-height, 56px); padding: 0 8px 0 16px;
  background: var(--app-header-background-color, var(--primary-color));
  color: var(--app-header-text-color, var(--text-primary-color, #fff));
  border-bottom: var(--app-header-border-bottom, none);
  box-sizing: border-box; position: sticky; top: 0; z-index: 2;
}
.toolbar .title { flex: 1; font-size: 20px; font-weight: 400; margin-left: 8px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.icon-btn, .tb-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  background: none; border: none; color: inherit; cursor: pointer; font: inherit;
  border-radius: 20px; height: 40px;
}
.icon-btn { width: 40px; margin-left: -8px; }
.toolbar .icon-btn[data-action="check"] { margin-left: 0; }
.tb-btn { padding: 0 12px; font-size: 14px; font-weight: 500; }
.icon-btn:hover, .tb-btn:hover { background: rgba(127, 127, 127, 0.15); }
.icon-btn:disabled { opacity: 0.6; cursor: default; }

.content { max-width: 1400px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
.summary { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 0; margin: 0 4px 12px; font-size: 14px; }
.summary .dot { margin: 0 10px; color: var(--secondary-text-color); }

.card {
  background: var(--ha-card-background, var(--card-background-color, #fff));
  border-radius: var(--ha-card-border-radius, 12px);
  border: 1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
  box-shadow: var(--ha-card-box-shadow, none);
  overflow: hidden;
}
.card-head { padding: 12px 16px; font-size: 14px; color: var(--secondary-text-color);
  border-bottom: 1px solid var(--divider-color); }
.empty { padding: 32px 24px; text-align: center; }
.empty p { margin: 8px auto; max-width: 560px; }
.big-icon svg { width: 48px; height: 48px; color: var(--secondary-text-color); }

table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; font-weight: 500; color: var(--secondary-text-color); font-size: 12px;
  padding: 10px 8px; white-space: nowrap; border-bottom: 1px solid var(--divider-color); }
td { padding: 10px 8px; vertical-align: middle; border-bottom: 1px solid var(--divider-color); }
tbody tr:last-child td { border-bottom: none; }
th:first-child, td:first-child { padding-left: 16px; }
th:last-child, td:last-child { padding-right: 16px; }
tr.has-update td:first-child { box-shadow: inset 3px 0 0 var(--warning-color, #ffa600); }
.device .name { font-weight: 500; }
.sub { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; max-width: 280px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub.ok { color: var(--success-color, #43a047); }
.sub.bad { color: var(--error-color, #db4437); }
td.actions { text-align: right; white-space: nowrap; }

select {
  font: inherit; font-size: 14px; color: var(--primary-text-color);
  background: var(--input-fill-color, var(--secondary-background-color, transparent));
  border: 1px solid var(--divider-color); border-radius: 8px; padding: 4px 8px;
}
select:disabled { opacity: 0.6; }

.btn {
  font: inherit; font-size: 14px; font-weight: 500; cursor: pointer;
  border-radius: 18px; padding: 6px 14px; margin-left: 4px;
  background: none; color: var(--primary-color);
  border: 1px solid var(--divider-color);
}
.btn:hover { background: rgba(127, 127, 127, 0.1); }
.btn.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
.btn.primary:hover { filter: brightness(1.08); }
.btn:disabled { opacity: 0.5; cursor: default; filter: none; }

.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500;
  padding: 3px 10px; border-radius: 12px; white-space: nowrap;
  background: rgba(127, 127, 127, 0.15); color: var(--secondary-text-color); }
.chip.success { background: rgba(67, 160, 71, 0.15); color: var(--success-color, #43a047); }
.chip.warning { background: rgba(255, 166, 0, 0.18); color: var(--warning-color, #ffa600); }
.chip.info { background: rgba(3, 155, 229, 0.15); color: var(--info-color, #039be5); }

.filter { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }
.filter .bar { width: 48px; height: 6px; border-radius: 3px; background: rgba(127, 127, 127, 0.2); overflow: hidden; }
.filter .bar span { display: block; height: 100%; background: var(--success-color, #43a047); }
.filter.low .bar span { background: var(--warning-color, #ffa600); }
.filter.bad .bar span { background: var(--error-color, #db4437); }

.spinner { width: 12px; height: 12px; border-radius: 50%; display: inline-block;
  border: 2px solid currentColor; border-right-color: transparent;
  animation: spin 0.8s linear infinite; vertical-align: middle; }
.spinner.light { width: 18px; height: 18px; }
@keyframes spin { to { transform: rotate(360deg); } }

.footer { font-size: 12px; text-align: center; margin: 16px 0 8px; }
.notice { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  margin: 0 0 12px; padding: 10px 16px; border-radius: 12px; font-size: 14px;
  background: rgba(3, 155, 229, 0.12); color: var(--primary-text-color); }
.notice .btn { margin-left: auto; }

.backdrop { position: fixed; inset: 0; z-index: 10; background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center; padding: 16px; }
.log { background: var(--ha-card-background, var(--card-background-color, #fff));
  color: var(--primary-text-color); border-radius: 12px; width: min(1000px, 100%);
  max-height: 85vh; display: flex; flex-direction: column; overflow: hidden; }
.log-head { display: flex; align-items: center; gap: 8px; padding: 12px 16px;
  border-bottom: 1px solid var(--divider-color); font-weight: 500; }
.log-head span { flex: 1; }
.log pre { margin: 0; padding: 12px 16px; overflow: auto; font-size: 12px; line-height: 1.45;
  font-family: var(--code-font-family, ui-monospace, Menlo, Consolas, monospace);
  white-space: pre-wrap; word-break: break-word; }

/* --- tabs and overview --- */
.tabs { display: flex; gap: 4px; margin: 0 4px 16px; border-bottom: 1px solid var(--divider-color); }
.tab { font: inherit; font-size: 14px; font-weight: 500; cursor: pointer; background: none; border: none;
  padding: 10px 14px; color: var(--secondary-text-color); border-bottom: 2px solid transparent; margin-bottom: -1px;
  display: inline-flex; align-items: center; gap: 6px; }
.tab:hover { color: var(--primary-text-color); }
.tab.on { color: var(--primary-color); border-bottom-color: var(--primary-color); }
.tab-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--warning-color, #ffa600); }
.overview { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.overview-note { margin: 16px 4px 0; font-size: 14px; }
.dcard { padding: 16px; cursor: pointer; outline: none; transition: border-color 0.15s, box-shadow 0.15s;
  background: var(--ha-card-background, var(--card-background-color, #fff));
  border-radius: var(--ha-card-border-radius, 12px);
  border: 1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0)); }
.dcard:hover { border-color: var(--primary-color); }
.dcard:focus-visible { box-shadow: 0 0 0 2px var(--primary-color); }
.dcard.offline { opacity: 0.6; }
.dc-top { display: flex; align-items: center; gap: 12px; }
.dev-img { width: 48px; height: 48px; flex: none; fill: rgba(127, 127, 127, 0.08); stroke: var(--secondary-text-color);
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.dcard.on .dev-img { stroke: var(--primary-color); fill: color-mix(in srgb, var(--primary-color) 12%, transparent); }
.dc-name { flex: 1; min-width: 0; }
.dc-name .name { font-size: 16px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dc-name .sub { max-width: none; }
.chip-btn { font: inherit; font-size: 12px; font-weight: 500; border: none; cursor: pointer; margin-left: auto; }
.chip-btn:hover { filter: brightness(0.95); }
.power.small { width: 44px; height: 44px; }
.power.small svg { width: 24px; height: 24px; }
.dc-mode { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; font-size: 14px; font-weight: 500; }
.dc-mode span:empty { display: none; }
.dc-controls { display: flex; flex-direction: column; gap: 6px; margin-top: 14px; }
.seg.sm { font-size: 12px; padding: 4px 10px; min-width: 30px; }
.dc-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
.dc-stat { padding: 8px 10px; border-radius: 10px; background: rgba(127, 127, 127, 0.08); min-width: 0; }
.dc-val { font-size: 18px; font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dc-val .unit { font-size: 11px; font-weight: 400; color: var(--secondary-text-color); margin-left: 3px; }
.dc-label { font-size: 12px; color: var(--secondary-text-color); }

/* --- device page --- */
.toolbar .back { margin-left: -8px; }
.page-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 4px 12px; }
.page-head .spacer { flex: 1; }
.page-head .btn, .empty .btn { display: inline-flex; align-items: center; gap: 6px; }
.page-head .btn svg, .empty .btn svg { width: 18px; height: 18px; }
.notice.warn { background: rgba(255, 166, 0, 0.16); }
.hint { font-size: 12px; font-weight: 400; color: var(--secondary-text-color); margin-top: 2px; }
.hint.pad, .muted.pad { padding: 4px 16px 12px; }

.hero { padding: 16px; margin-bottom: 16px; }
.hero-controls { display: flex; align-items: center; gap: 16px; }
.hero-rows { flex: 1; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.hero-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.h-label { width: 48px; font-size: 12px; color: var(--secondary-text-color); }
.power { width: 64px; height: 64px; border-radius: 50%; cursor: pointer; flex: none;
  border: 1px solid var(--divider-color); background: none; color: var(--secondary-text-color);
  display: inline-flex; align-items: center; justify-content: center; }
.power svg { width: 32px; height: 32px; }
.power.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
.power:disabled { opacity: 0.5; cursor: default; }
.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; margin-top: 16px; }
.tile { padding: 10px 12px; border-radius: 10px; background: rgba(127, 127, 127, 0.08); }
.t-val { font-size: 22px; font-weight: 500; font-variant-numeric: tabular-nums; }
.t-val .unit { font-size: 12px; font-weight: 400; color: var(--secondary-text-color); margin-left: 4px; }
.t-label { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
.hero .setting { padding-left: 0; padding-right: 0; }

.segs { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.seg { font: inherit; font-size: 13px; cursor: pointer; padding: 6px 12px; border-radius: 16px;
  border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); min-width: 36px; }
.seg:hover { background: rgba(127, 127, 127, 0.1); }
.seg.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
.seg:disabled { opacity: 0.5; cursor: default; }

.sections { columns: 2 420px; column-gap: 16px; }
.section { break-inside: avoid; margin-bottom: 16px; }
.sec-head { padding: 12px 16px; font-size: 16px; font-weight: 500; border-bottom: 1px solid var(--divider-color); }
details.section > summary { cursor: pointer; list-style: none; display: flex; align-items: center; justify-content: space-between; }
details.section > summary svg { color: var(--secondary-text-color); transition: transform 0.15s; }
details.section[open] > summary svg { transform: rotate(180deg); }
details.section > summary:hover { background: rgba(127, 127, 127, 0.06); }
details.section > summary::-webkit-details-marker { display: none; }
details.section:not([open]) > summary { border-bottom: none; }
.subhead { padding: 12px 16px 0; font-size: 12px; font-weight: 500; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--secondary-text-color); }
.setting { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px; }
.setting + .setting { border-top: 1px solid rgba(127, 127, 127, 0.12); }
.setting.dim .s-label { opacity: 0.55; }
.s-label { font-size: 14px; min-width: 0; }
.s-control { flex: none; max-width: 65%; display: flex; justify-content: flex-end; }
.readout { font-variant-numeric: tabular-nums; color: var(--secondary-text-color); text-align: right; }

.switch { position: relative; width: 40px; height: 22px; border-radius: 11px; cursor: pointer; padding: 0;
  border: none; background: rgba(127, 127, 127, 0.35); transition: background 0.15s; flex: none; }
.switch span { position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%;
  background: #fff; transition: transform 0.15s; }
.switch.on { background: var(--primary-color); }
.switch.on span { transform: translateX(18px); }
.switch:disabled { opacity: 0.45; cursor: default; }

.slider { display: flex; align-items: center; gap: 10px; }
.slider input { width: 160px; accent-color: var(--primary-color); }
.val { font-variant-numeric: tabular-nums; min-width: 64px; text-align: right; font-size: 14px; }
.stepper { display: inline-flex; align-items: center; gap: 6px; }
.stepper .val { min-width: 80px; text-align: center; }
.step { width: 32px; height: 32px; border-radius: 50%; cursor: pointer; font: inherit; font-size: 18px; line-height: 1;
  border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); }
.step:disabled { opacity: 0.4; cursor: default; }
.times { display: inline-flex; align-items: center; gap: 6px; }
.times input { font: inherit; font-size: 14px; color: var(--primary-text-color); padding: 4px 6px;
  background: var(--input-fill-color, var(--secondary-background-color, transparent));
  border: 1px solid var(--divider-color); border-radius: 8px; }

.timer-run, .filter-big { padding: 12px 16px 4px; }
.timer-run .big, .filter-big .big { font-size: 24px; font-weight: 500; font-variant-numeric: tabular-nums; }
.timer-run .big .muted { font-size: 14px; font-weight: 400; }
.timer-run .bar, .filter-big .bar { height: 6px; border-radius: 3px; margin-top: 8px; overflow: hidden;
  background: rgba(127, 127, 127, 0.2); }
.timer-run .bar span, .filter-big .bar span { display: block; height: 100%; background: var(--primary-color); }
.filter-big .bar span { background: var(--success-color, #43a047); }
.filter-big.low .bar span { background: var(--warning-color, #ffa600); }
.filter-big.bad .bar span { background: var(--error-color, #db4437); }

.history { margin-bottom: 16px; }
.hist-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.hist-head .segs { font-size: 14px; font-weight: 400; }
.hist { position: relative; margin: 0 16px 12px; outline: none; transition: opacity 0.2s; }
.hist:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 4px; border-radius: 4px; }
.hist.stale { opacity: 0.5; }
.hist-title { display: flex; justify-content: space-between; align-items: baseline;
  margin: 12px 0 4px 40px; font-size: 13px; color: var(--secondary-text-color); }
.hist-now { color: var(--primary-text-color); font-weight: 500; font-variant-numeric: tabular-nums; }
.hist-row { display: grid; grid-template-columns: 40px 1fr; }
.hist-y { position: relative; }
.ytick { position: absolute; right: 8px; transform: translateY(-50%); font-size: 11px;
  color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
.hist-plot { display: block; width: 100%; height: 76px; overflow: visible; }
.hist-plot .grid { stroke: var(--divider-color); stroke-width: 1; vector-effect: non-scaling-stroke; }
.hist-plot .area { fill: var(--primary-color); fill-opacity: 0.1; stroke: none; }
.hist-plot .line { fill: none; stroke: var(--primary-color); stroke-width: 2; stroke-linejoin: round;
  stroke-linecap: round; vector-effect: non-scaling-stroke; }
.hist-plot .line.dot { stroke-width: 4; }
.hist-plot .xhair { stroke: var(--secondary-text-color); stroke-width: 1; vector-effect: non-scaling-stroke; }
.hist-empty { margin-left: 40px; padding: 8px 0; font-size: 13px; }
.hist-axis { position: relative; height: 20px; }
.xtick { position: absolute; top: 4px; transform: translateX(-50%); font-size: 11px; white-space: nowrap;
  color: var(--secondary-text-color); }
.hist-tip { position: absolute; top: 28px; z-index: 1; pointer-events: none; min-width: 120px;
  padding: 6px 10px; border-radius: 8px; font-size: 12px;
  background: var(--ha-card-background, var(--card-background-color, #fff));
  border: 1px solid var(--divider-color); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18); }
.tip-time { color: var(--secondary-text-color); margin-bottom: 4px; }
.tip-row { display: flex; justify-content: space-between; gap: 12px; line-height: 1.6; }
.tip-row strong { font-weight: 600; font-variant-numeric: tabular-nums; }
.tip-row span { color: var(--secondary-text-color); }

@media (max-width: 600px) {
  .hero-controls { flex-direction: column; align-items: stretch; }
  .power { align-self: center; }
  .setting { flex-wrap: wrap; }
  .s-control { max-width: 100%; }
  .slider input { width: 120px; }
}

@media (max-width: 1100px) {
  .tb-btn span { display: none; }
  .tb-btn { width: 40px; padding: 0; }
  table, tbody { display: block; }
  thead { display: none; }
  tr { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px;
    padding: 12px 16px; border-bottom: 1px solid var(--divider-color); }
  tbody tr:last-child { border-bottom: none; }
  tr.has-update { box-shadow: inset 3px 0 0 var(--warning-color, #ffa600); }
  tr.has-update td:first-child { box-shadow: none; }
  td { display: block; padding: 0 !important; border: none; }
  td[data-label]::before { content: attr(data-label); display: block; font-size: 11px;
    color: var(--secondary-text-color); margin-bottom: 1px; }
  td.device { grid-column: 1 / -1; }
  td.device::before { display: none !important; }
  td.device .name { font-size: 16px; }
  td.actions { grid-column: 1 / -1; text-align: left; display: flex; gap: 8px; margin-top: 4px; }
  td.actions .btn { margin: 0; flex: 1; }
}
@media (max-width: 420px) {
  .content { padding: 8px; }
  tr { grid-template-columns: 1fr; }
}
`;

customElements.get("levoit-esphome-panel") ||
  customElements.define("levoit-esphome-panel", LevoitEsphomePanel);
