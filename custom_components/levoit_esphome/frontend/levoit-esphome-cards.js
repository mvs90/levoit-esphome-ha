// Levoit ESPHome dashboard cards. Loaded on every Home Assistant page by the
// integration (no resource to add): custom:levoit-purifier-card for now; the
// group and list cards follow.
//
// The cards read entity states and call fan services only. Which entities
// belong to a purifier (PM2.5, AQI, CADR, filter, its group) comes once from
// levoit_esphome/cards, which any user may call.

const DOC_URL = "https://github.com/tuct/levoit-esphome-ha#dashboard-cards";

const ICONS = {
  purifier:
    "M16,2H8A2,2 0 0,0 6,4V20A2,2 0 0,0 8,22H16A2,2 0 0,0 18,20V4A2,2 0 0,0 16,2M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4M16,20H8V18H16V20M16,16H8V14H16V16M16,12H8V10H16V12Z",
  power:
    "M16.56,5.44L15.11,6.89C16.84,7.94 18,9.83 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12C6,9.83 7.16,7.94 8.88,6.88L7.44,5.44C5.36,6.88 4,9.28 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,9.28 18.64,6.88 16.56,5.44M13,3H11V13H13",
  group:
    "M20,16V4H8V16H20M22,16A2,2 0 0,1 20,18H8C6.89,18 6,17.1 6,16V4C6,2.89 6.89,2 8,2H20A2,2 0 0,1 22,4V16M16,20V22H4A2,2 0 0,1 2,20V7H4V20H16Z",
  filter:
    "M14,12V19.88C14.04,20.18 13.94,20.5 13.71,20.71C13.32,21.1 12.69,21.1 12.3,20.71L10.29,18.7C10.06,18.47 9.96,18.16 10,17.87V12H9.97L4.21,4.62C3.87,4.19 3.95,3.56 4.38,3.22C4.57,3.08 4.78,3 5,3H19C19.22,3 19.43,3.08 19.62,3.22C20.05,3.56 20.13,4.19 19.79,4.62L14.03,12H14Z",
  chevron: "M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z",
};
const icon = (name, cls = "") =>
  `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name]}"></path></svg>`;

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

// the purifiers' air quality level, 1 (very good) to 4 (poor)
const AQI_WORDS = { 1: "Very good", 2: "Good", 3: "Moderate", 4: "Poor" };
const usable = (st) => Boolean(st) && st.state !== "unavailable" && st.state !== "unknown";
const numberOf = (st) => {
  if (!usable(st)) return null;
  const v = parseFloat(st.state);
  return Number.isFinite(v) ? v : null;
};
const whole = (v) => (v == null ? "—" : String(Math.round(v)));
const levelOf = (v) => {
  const n = Math.round(Number(v));
  return n >= 1 && n <= 4 ? n : null;
};

// levoit_esphome/cards: which entities make up each purifier and group. One
// request for all cards on a page, again after a minute.
let snapshot = null;
const loadSnapshot = (hass, force = false) => {
  if (!force && snapshot && snapshot.connection === hass.connection && Date.now() - snapshot.at < 60e3)
    return snapshot.promise;
  const promise = hass.callWS({ type: "levoit_esphome/cards" });
  snapshot = { connection: hass.connection, at: Date.now(), promise };
  promise.catch(() => {
    if (snapshot?.promise === promise) snapshot = null;
  });
  return promise;
};

// A purifier's fan as the cards show it. Turbo is a speed, also where the
// device reports it as a mode (Everest Air); the Eleva's level 4 is Turbo.
const fanView = (st, model) => {
  const a = st?.attributes || {};
  const presets = a.preset_modes || [];
  const step = Number(a.percentage_step) || 25;
  const count = Math.max(1, Math.round(100 / step));
  const speeds = Array.from({ length: count }, (_, i) => ({ value: i + 1, label: String(i + 1) }));
  const turboMode = presets.includes("Turbo");
  if (turboMode) speeds.push({ value: "turbo", label: "Turbo" });
  else if (model === "ELEVA300X" && count === 4) speeds[3].label = "Turbo";
  const modes = presets.filter((p) => p !== "Turbo");
  const offline = !usable(st);
  const on = st?.state === "on";
  const preset = a.preset_mode;
  // Manual (or Turbo, its top speed): the speed buttons show what it runs at
  const manual = on && (!modes.length || !preset || preset === "Manual" || preset === "Turbo");
  const speed = !on
    ? null
    : preset === "Turbo"
      ? "turbo"
      : Math.round((Number(a.percentage) || 0) / step) || null;
  const speedLabel = speeds.find((s) => s.value === speed)?.label || "";
  const mode = preset === "Turbo" ? "Manual" : preset || "";
  const state = offline
    ? "Unavailable"
    : !on
      ? "Off"
      : manual
        ? `Manual${speedLabel ? ` · ${speedLabel}` : ""}`
        : preset || "On";
  return { count, speeds, modes, offline, on, manual, speed, speedLabel, mode, state };
};

const BASE_STYLE = `
:host { display: block; height: 100%; }
ha-card { height: 100%; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column;
  --lv-q1: #43a047; --lv-q2: #c0ca33; --lv-q3: #ffa000; --lv-q4: #c62828;
  --lv-track: var(--secondary-background-color, rgba(127, 127, 127, 0.12)); }
.i { width: 20px; height: 20px; fill: currentColor; flex: none; }
.trunc { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.muted { color: var(--secondary-text-color); }
.icn { width: 40px; height: 40px; border-radius: 50%; border: 0; padding: 0; flex: none; display: inline-flex;
  align-items: center; justify-content: center; background: var(--lv-track); color: var(--secondary-text-color);
  cursor: pointer; }
.icn.on { background: color-mix(in srgb, var(--primary-color) 18%, transparent); color: var(--primary-color); }
.icn.offline { opacity: 0.5; }
.icn.sm { width: 36px; height: 36px; } .icn.xs { width: 32px; height: 32px; } .icn.xs .i { width: 16px; height: 16px; }
.pwr { width: 40px; height: 40px; border-radius: 50%; border: 1.5px solid var(--divider-color); background: transparent;
  color: var(--secondary-text-color); display: inline-flex; align-items: center; justify-content: center; padding: 0;
  cursor: pointer; flex: none; }
.pwr.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.pwr:disabled, .icn:disabled { opacity: 0.45; cursor: not-allowed; }
.seg { display: flex; gap: 2px; padding: 2px; border-radius: 12px; background: var(--lv-track); min-width: 0; }
.seg button { flex: 1; height: 36px; min-width: 32px; padding: 0 6px; border: 0; border-radius: 10px; background: transparent;
  color: var(--secondary-text-color); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; white-space: nowrap; }
.seg button.on { background: var(--card-background-color, #fff); color: var(--primary-color);
  box-shadow: inset 0 0 0 1.5px var(--primary-color); }
.seg.dim button.on { box-shadow: inset 0 0 0 1.5px var(--divider-color); color: var(--secondary-text-color); }
.seg button:disabled { opacity: 0.45; cursor: not-allowed; }
.sel { position: relative; display: inline-flex; flex: none; }
.sel select { appearance: none; -webkit-appearance: none; height: 40px; padding: 0 30px 0 12px; border-radius: 12px;
  border: 1px solid var(--divider-color); background: var(--card-background-color, #fff); color: var(--primary-text-color);
  font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; }
.sel select:disabled { opacity: 0.45; cursor: not-allowed; }
.sel .i { position: absolute; right: 8px; top: 10px; pointer-events: none; color: var(--secondary-text-color); }
.stat { background: var(--lv-track); border-radius: 10px; padding: 8px 10px; min-width: 0; }
.stat b { display: flex; align-items: center; gap: 6px; font-size: 20px; font-weight: 500; }
.stat span { font-size: 11px; color: var(--secondary-text-color); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; display: inline-block; background: var(--divider-color); }
.dot.q1 { background: var(--lv-q1); } .dot.q2 { background: var(--lv-q2); }
.dot.q3 { background: var(--lv-q3); } .dot.q4 { background: var(--lv-q4); }
.chip { display: inline-flex; align-items: center; gap: 4px; height: 18px; padding: 0 7px; border-radius: 9px; font-size: 11px;
  font-weight: 500; white-space: nowrap; background: color-mix(in srgb, var(--primary-color) 14%, transparent);
  color: var(--primary-color); }
.chip .i { width: 11px; height: 11px; }
.off-pill { display: inline-flex; align-items: center; gap: 5px; height: 18px; padding: 0 8px; border-radius: 9px; font-size: 11px;
  font-weight: 500; background: color-mix(in srgb, var(--error-color, #db4437) 14%, transparent);
  color: var(--error-color, #db4437); flex: none; }
.fbar { display: inline-block; width: 24px; height: 4px; border-radius: 2px; background: var(--divider-color); overflow: hidden; }
.fbar span { display: block; height: 100%; background: var(--success-color, #43a047); }
.fbar.low span { background: var(--warning-color, #ffa600); } .fbar.bad span { background: var(--error-color, #db4437); }
.low-text { color: var(--warning-color, #ffa600); } .bad-text { color: var(--error-color, #db4437); }
.msg { padding: 16px; color: var(--secondary-text-color); font-size: 14px; }
`;

class LevoitCardBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._snap = null;
    this._key = "";
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
    this._key = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._snap && !this._loading) this._load();
    // render only when a state the card shows has changed
    const key = this._watched()
      .map((id) => {
        const st = hass.states[id];
        return st ? `${st.state}@${st.last_updated}` : "-";
      })
      .join("|");
    if (key !== this._key) {
      this._key = key;
      this._render();
    }
  }

  async _load(force = false) {
    this._loading = true;
    try {
      this._snap = await loadSnapshot(this._hass, force);
      this._error = null;
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._key = "";
      this._render();
    }
  }

  // the size in the sections view: its grid columns (of 12) and rows
  _size(defaultRows) {
    const g = this._config?.grid_options || {};
    const rows = Number(g.rows) || defaultRows;
    const columns = g.columns === "full" ? 12 : Number(g.columns) || 12;
    return { rows, columns };
  }

  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
  }

  _watched() {
    return [];
  }

  _onClick() {}

  _onChange() {}
}

// --- the purifier card --------------------------------------------------------------

const PURIFIER_SHOW = ["pm25", "aqi", "cadr", "filter", "group"];
const PURIFIER_CONTROLS = ["speed", "mode"];

class LevoitPurifierCard extends LevoitCardBase {
  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "fan", integration: "esphome" } } },
        { name: "name", selector: { text: {} } },
        {
          name: "show",
          selector: {
            select: {
              multiple: true,
              mode: "list",
              options: [
                { value: "pm25", label: "PM2.5" },
                { value: "aqi", label: "AQI" },
                { value: "cadr", label: "CADR" },
                { value: "filter", label: "Filter" },
                { value: "group", label: "Group" },
              ],
            },
          },
        },
        {
          name: "controls",
          selector: {
            select: {
              multiple: true,
              mode: "list",
              options: [
                { value: "speed", label: "Speed" },
                { value: "mode", label: "Mode" },
              ],
            },
          },
        },
      ],
      computeLabel: (s) => ({ entity: "Purifier (its fan)", name: "Name", show: "Show", controls: "Controls" })[s.name],
      computeHelper: (s) =>
        s.name === "entity" ? "The fan of a Levoit purifier with the tuct/levoit component" : undefined,
    };
  }

  static getStubConfig(hass) {
    const fans = Object.keys(hass?.states || {}).filter(
      (id) => id.startsWith("fan.") && hass.entities?.[id]?.platform === "esphome",
    );
    return { entity: fans[0] || "" };
  }

  getCardSize() {
    const { rows } = this._size(4);
    return rows <= 1 ? 1 : rows <= 3 ? 2 : 5;
  }

  getGridOptions() {
    return { columns: 12, rows: 4, min_columns: 3, min_rows: 1 };
  }

  get _purifier() {
    return (this._snap?.purifiers || []).find((p) => p.entity_id === this._config?.entity) || null;
  }

  _watched() {
    const p = this._purifier;
    return [this._config?.entity, p?.pm25, p?.aqi, p?.cadr, p?.filter].filter(Boolean);
  }

  _onClick(ev) {
    const el = ev.target.closest("[data-act]");
    if (!el || el.disabled) return;
    const entity = this._config.entity;
    const view = fanView(this._hass.states[entity], this._purifier?.model);
    const act = el.dataset.act;
    if (act === "more") this._moreInfo(entity);
    else if (act === "power") this._call("fan", view.on ? "turn_off" : "turn_on", { entity_id: entity });
    else if (act === "speed") {
      const value = el.dataset.value;
      if (value === "turbo") this._call("fan", "set_preset_mode", { entity_id: entity, preset_mode: "Turbo" });
      // the lowest percentage of that speed: 33 / 66 / 100 for 3 speeds
      else
        this._call("fan", "set_percentage", {
          entity_id: entity,
          percentage: Math.floor((Number(value) * 100) / view.count),
        });
    } else if (act === "mode") this._call("fan", "set_preset_mode", { entity_id: entity, preset_mode: el.dataset.value });
  }

  _onChange(ev) {
    const sel = ev.target.closest("select[data-act='mode']");
    if (!sel) return;
    sel.blur();
    this._call("fan", "set_preset_mode", { entity_id: this._config.entity, preset_mode: sel.value });
  }

  _render() {
    if (!this._config) return;
    const hass = this._hass;
    const entity = this._config.entity;
    const st = hass?.states?.[entity];
    let body;
    if (!hass) body = "";
    else if (!entity || !st) body = `<div class="msg">${esc(entity ? `${entity} not found` : "Pick a purifier")}</div>`;
    else body = this._body(st);
    this.shadowRoot.innerHTML = `<style>${BASE_STYLE}${PURIFIER_STYLE}</style><ha-card>${body}</ha-card>`;
  }

  _body(st) {
    const c = this._config;
    const p = this._purifier;
    const hass = this._hass;
    const show = new Set(c.show || PURIFIER_SHOW);
    const controls = new Set(c.controls || PURIFIER_CONTROLS);
    const v = fanView(st, p?.model);
    const name = c.name || p?.title || st.attributes.friendly_name || c.entity;
    const pm = show.has("pm25") && p?.pm25 ? numberOf(hass.states[p.pm25]) : null;
    const aqi = show.has("aqi") && p?.aqi ? levelOf(numberOf(hass.states[p.aqi])) : null;
    const cadr = show.has("cadr") && p?.cadr ? numberOf(hass.states[p.cadr]) : null;
    const filter = show.has("filter") && p?.filter ? numberOf(hass.states[p.filter]) : null;
    const group = show.has("group") && p?.group_id ? (this._snap?.groups || []).find((g) => g.id === p.group_id) : null;
    const dis = v.offline ? "disabled" : "";
    const { rows, columns } = this._size(4);
    const layout = rows <= 1 ? "compact" : rows <= 3 ? "small" : columns >= 9 ? "large" : "medium";

    const iconBtn = (cls, act, label) =>
      `<button class="icn ${cls}${v.offline ? " offline" : v.on ? " on" : ""}" data-act="${act}" aria-label="${esc(label)}" ${
        act === "power" ? dis : ""
      }>${icon("purifier")}</button>`;
    const power = `<button class="pwr${v.on ? " on" : ""}" data-act="power" aria-pressed="${v.on}" aria-label="Power" ${dis}>${icon(
      "power",
    )}</button>`;
    const speedSeg = () =>
      controls.has("speed")
        ? `<div class="seg${v.manual ? "" : " dim"}" role="group" aria-label="Speed">${v.speeds
            .map((s) => {
              const cur = v.on && s.value === v.speed;
              return `<button class="${cur ? "on" : ""}" aria-pressed="${cur}" data-act="speed" data-value="${s.value}" ${dis}>${esc(
                s.label,
              )}</button>`;
            })
            .join("")}</div>`
        : "";
    const modeSeg = () =>
      controls.has("mode") && v.modes.length
        ? `<div class="seg" role="group" aria-label="Mode">${v.modes
            .map((m) => {
              const cur = v.on && m === v.mode;
              return `<button class="${cur ? "on" : ""}" aria-pressed="${cur}" data-act="mode" data-value="${esc(m)}" ${dis}>${esc(
                m,
              )}</button>`;
            })
            .join("")}</div>`
        : "";
    const modeSelect = () =>
      controls.has("mode") && v.modes.length
        ? `<span class="sel"><select data-act="mode" aria-label="Mode" ${dis}>${[...(v.on ? [] : [""]), ...v.modes]
            .map((m) => `<option value="${esc(m)}"${m === (v.on ? v.mode : "") ? " selected" : ""}>${esc(m || "Off")}</option>`)
            .join("")}</select>${icon("chevron")}</span>`
        : "";
    const filterLevel = filter == null ? "" : filter < 10 ? "bad" : filter < 25 ? "low" : "";
    const filterBar =
      filter == null
        ? ""
        : `<span class="filt" role="img" aria-label="Filter ${whole(filter)} % left">${icon("filter")}<span class="fbar ${filterLevel}"><span style="width:${Math.max(
            0,
            Math.min(100, filter),
          )}%"></span></span>${whole(filter)} %</span>`;
    const groupChip = group ? `<span class="chip">${icon("group")}${esc(group.name)}</span>` : "";
    const offlinePill = v.offline ? `<span class="off-pill"><span class="dot"></span>Offline</span>` : "";

    if (layout === "compact") {
      const narrow = columns <= 3;
      const parts = narrow
        ? [pm != null ? whole(pm) : null, v.on ? v.speedLabel || v.mode : v.state].filter(Boolean)
        : [v.state, pm != null ? `${whole(pm)} µg/m³` : null].filter(Boolean);
      return `<div class="compact${narrow ? " narrow" : ""}" data-act="more" role="button" tabindex="0" aria-label="${esc(name)}">
        ${iconBtn(narrow ? "xs" : "sm", "power", `Power ${name}`)}
        <div class="who"><div class="trunc nm">${esc(name)}</div><div class="trunc muted st${v.offline ? " bad-text" : ""}">${esc(
          v.offline ? "Offline" : parts.join(" · "),
        )}</div></div>
      </div>`;
    }
    if (layout === "small")
      return `<div class="small">
        <div class="head">${iconBtn("", "power", `Power ${name}`)}
          <div class="who" data-act="more"><div class="trunc nm">${esc(name)}</div><div class="trunc muted st">${esc(
            [v.state, pm != null ? `${whole(pm)} µg/m³` : null].filter(Boolean).join(" · "),
          )}</div></div>${offlinePill}</div>
        ${speedSeg()}
      </div>`;
    if (layout === "medium") {
      const facts = [
        cadr != null ? `<span>CADR <b>${whole(cadr)}</b> m³/h</span>` : "",
        filter != null ? `<span>Filter <b class="${filterLevel ? `${filterLevel}-text` : ""}">${whole(filter)} %</b></span>` : "",
        groupChip,
      ].join("");
      return `<div class="medium">
        <div class="head">${iconBtn("", "more", `Open ${name}`)}
          <div class="who"><div class="trunc nm">${esc(name)}</div><div class="trunc muted st">${esc(v.state)}</div></div>
          ${offlinePill || power}</div>
        ${
          pm != null || aqi
            ? `<div class="big">${pm != null ? `<b>${whole(pm)}</b><span class="muted">PM2.5 µg/m³</span>` : ""}${
                aqi ? `<span class="lvl"><span class="dot q${aqi}"></span><span class="muted">${esc(AQI_WORDS[aqi])}</span></span>` : ""
              }</div>`
            : ""
        }
        ${facts.trim() ? `<div class="facts">${facts}</div>` : ""}
        <div class="ctl">${speedSeg()}${modeSeg()}</div>
      </div>`;
    }
    // large
    const stats = [
      pm != null ? `<div class="stat"><b>${whole(pm)}</b><span>PM2.5 µg/m³</span></div>` : "",
      aqi ? `<div class="stat"><b>${aqi} <span class="dot q${aqi}"></span></b><span>AQI · ${esc(AQI_WORDS[aqi])}</span></div>` : "",
      cadr != null ? `<div class="stat"><b>${whole(cadr)}</b><span>CADR m³/h</span></div>` : "",
    ].filter(Boolean);
    const status = [esc(v.state), groupChip, filterBar].filter(Boolean).join(`<span aria-hidden="true">·</span>`);
    return `<div class="large">
      <div class="head">${iconBtn("", "more", `Open ${name}`)}
        <div class="who"><div class="trunc nm lg">${esc(name)}</div><div class="status muted">${status}</div></div>
        ${offlinePill || power}</div>
      ${stats.length ? `<div class="stats" style="--n:${stats.length}">${stats.join("")}</div>` : ""}
      <div class="ctl row">${speedSeg()}${modeSelect()}</div>
    </div>`;
  }
}

const PURIFIER_STYLE = `
.large, .medium, .small { display: flex; flex-direction: column; height: 100%; box-sizing: border-box; }
.large { padding: 14px 16px; gap: 12px; }
.medium { padding: 12px; gap: 10px; }
.small { padding: 10px; gap: 8px; }
.head { display: flex; align-items: center; gap: 12px; min-width: 0; }
.medium .head, .small .head { gap: 10px; }
.who { flex: 1; min-width: 0; cursor: pointer; }
.nm { font-size: 14px; font-weight: 500; }
.nm.lg { font-size: 16px; }
.st { font-size: 12px; margin-top: 1px; }
.status { display: flex; align-items: center; gap: 6px; margin-top: 3px; font-size: 12px; flex-wrap: wrap; }
.filt { display: inline-flex; align-items: center; gap: 4px; }
.filt .i { width: 11px; height: 11px; }
.stats { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 8px; }
.big { display: flex; align-items: baseline; gap: 6px; padding: 2px 2px 0; }
.big b { font-size: 34px; font-weight: 500; line-height: 1; }
.big span { font-size: 12px; }
.big .lvl { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; align-self: center; }
.facts { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; font-size: 12px; color: var(--secondary-text-color); padding: 0 2px; }
.facts b { font-weight: 500; color: var(--primary-text-color); }
.facts b.low-text { color: var(--warning-color, #ffa600); } .facts b.bad-text { color: var(--error-color, #db4437); }
.ctl { display: flex; flex-direction: column; gap: 8px; margin-top: auto; }
.ctl.row { flex-direction: row; align-items: center; }
.ctl.row .seg { flex: 1; }
.small .seg { margin-top: auto; }
.compact { height: 100%; box-sizing: border-box; padding: 0 10px; display: flex; align-items: center; gap: 10px; cursor: pointer; }
.compact.narrow { padding: 0 8px; gap: 8px; }
.compact.narrow .nm { font-size: 13px; }
`;

customElements.get("levoit-purifier-card") || customElements.define("levoit-purifier-card", LevoitPurifierCard);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "levoit-purifier-card"))
  window.customCards.push({
    type: "levoit-purifier-card",
    name: "Levoit purifier",
    description: "A Levoit purifier: power, PM2.5, AQI, CADR, filter, speed and mode. From 12 × 4 down to 3 × 1.",
    preview: true,
    documentationURL: DOC_URL,
  });
