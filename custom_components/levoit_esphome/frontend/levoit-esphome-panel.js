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
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
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
    if (first) this._render();
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
    return this._data?.devices.find((d) => d.name === name);
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
    const deviceLink = d.device_id
      ? `<a href="/config/devices/device/${esc(d.device_id)}" data-action="navigate" data-path="/config/devices/device/${esc(d.device_id)}">${esc(d.title)}</a>`
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
    if (!devices.length)
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
        }</span>
      </div>
      <table>
        <thead><tr>
          <th>Device</th><th>Model</th><th>ESP / config</th><th>Channel</th>
          <th>Installed</th><th>Latest</th><th>Filter</th><th>ESPHome</th><th>Status</th><th></th>
        </tr></thead>
        <tbody>${devices.map((d) => this._row(d)).join("")}</tbody>
      </table>
    </div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    // do not pull an open channel dropdown away from under the pointer
    if (this.shadowRoot.activeElement?.tagName === "SELECT") {
      this._deferred = true;
      return;
    }
    const showMenu = this._narrow || this._hass?.dockedSidebar === "always_hidden";
    const builderUrl = this._data?.builder_url;
    const version = this._panel?.config?.version;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar">
        ${
          showMenu
            ? `<button class="icon-btn" data-action="menu" aria-label="Menu">${icon("menu")}</button>`
            : ""
        }
        <div class="title">Levoit ESPHome</div>
        <button class="icon-btn" data-action="check" ${this._checking ? "disabled" : ""} title="Check for new versions now" aria-label="Check for new versions now">${
          this._checking ? `<span class="spinner light"></span>` : icon("refresh")
        }</button>
        ${
          builderUrl
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
        <div class="summary">${this._summary()}</div>
        ${this._body()}
        <div class="footer muted">Levoit ESPHome${version ? ` ${esc(version)}` : ""} ·
          builds run in the ESPHome Device Builder; the last build's output is under Log</div>
      </div>
      ${this._logDialog()}`;
    const pre = this.shadowRoot.querySelector(".log pre");
    if (pre) pre.scrollTop = pre.scrollHeight; // newest lines in view
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
