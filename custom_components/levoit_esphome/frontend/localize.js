import de from "./translations/de.js";

const catalogs = { de };

export const language = (hass) =>
  hass?.locale?.language || hass?.language || globalThis.document?.documentElement?.lang || "en";

export function interpolate(text, params) {
  if (!params) return text;
  return text.replace(/\{([A-Za-z][A-Za-z0-9]*)\}/g, (placeholder, name) =>
    Object.hasOwn(params, name) ? String(params[name] ?? "") : placeholder,
  );
}

export function translate(hass, message, params) {
  const locale = language(hass).split("-")[0].toLowerCase();
  const catalog = Object.hasOwn(catalogs, locale) ? catalogs[locale] : null;
  const text = catalog && Object.hasOwn(catalog, message) ? catalog[message] : message ?? "";
  return interpolate(text, params);
}
