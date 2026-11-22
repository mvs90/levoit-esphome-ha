# Levoit ESPHome

A Home Assistant integration for air purifiers and humidifiers running the
[`levoit`](https://github.com/tuct/levoit) or `philips` ESPHome components.

It finds every ESPHome device built with those components, links it to its
config in the ESPHome Device Builder, and offers an update when the device's
channel has a newer component version. Installing compiles the config in the
Device Builder and uploads it over the air.

![The Levoit ESPHome sidebar page: each device with model, ESP, channel, installed and latest version, filter %, status, Compile and Compile & upload](https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/panel.png)

> **Early version.** Part of the
> [firmware update plan](https://github.com/tuct/levoit/blob/main/docs/firmware-updates.md).

## What you get

Per purifier, on a device of the same name (its *Visit* link opens the ESPHome Device Builder); Home Assistant lists the purifier's
ESPHome device under *Linked devices* (same MAC address). Since Home Assistant
2026.8 an integration cannot add entities to another integration's device.

**With a config in the Device Builder** the integration reads model and
channel from it and can install updates; for a template config the *Update
channel* select switches the channel. **Without one** it still shows whether
an update is out: pick the channel in the device's *Update channel* select
(default `stable`); the model comes from the device's `model` text sensor.
Installing and compiling need the config.

| Entity | What it shows / does |
|--------|----------------------|
| **Component firmware** (update) | Installed component version against the newest one on the device's channel; release notes; *Install* compiles and uploads |
| **Compile firmware** (button) | Compiles in the Device Builder without uploading |
| **Compile and upload** (button) | Compiles and uploads over the air at any time, also when the device is up to date (a template config is refreshed from the newest builder file first, like *Install*) |
| **Filter life** | The purifier's filter % from its own ESPHome filter sensor (`%` with the `mdi:air-filter` icon or "filter" in its name; HEPA over pre-filter) |
| **Installed component version** | What the device reports, e.g. `1.7.0` or `1.7.0+3fa21c4` |
| **Latest component version** | Newest version on the device's channel (release + commit), *unknown* without a channel |
| **Component model** | `model:` from the config, else from the device's `model` text sensor, e.g. `CORE300S` |
| **Firmware channel** | `stable` (releases), `main` (every merge), `pinned` (another ref or a fork) or `local`; from the config, else the select below |
| **Update channel** (select) | `stable` / `main`. Without a Device Builder config: which channel to compare the device with. With a template config: rewrites `ref:` in the config, the next install builds from it. Unavailable for a custom config: change its `ref:` yourself |
| **Device Builder config** | The config file the device is built from |
| **Config type** | `original` / `xiao_c3` / `c3`: made from a template; `custom`: your own config |

A newer **ESPHome** version is already offered by Home Assistant's own ESPHome
firmware update; this integration adds the component version.

## Sidebar page

Turn on **Settings → Devices & services → Levoit ESPHome → ⚙ (Configure) →
Show in the sidebar** for a *Levoit ESPHome* page, visible to admins only:

* every device: model, ESP / config type, channel, installed and latest
  component version, filter %, ESPHome version, status and the last build
* **Compile** and **Compile and upload** (*Update* when one is out), with the
  result per device; the build log stays in the Device Builder
* the channel of a device without a config or with a template config
* links to each device, the Device Builder and Add device; *check now* reads
  the latest versions from GitHub without waiting for the 6 hours

The page updates live. It is a plain web component served by the integration;
nothing is loaded from outside Home Assistant.

## Add device

**Settings → Devices & services → Levoit ESPHome → Add device** makes a Device
Builder config from a template of tuct/levoit
([`devices/templates.json`](https://github.com/tuct/levoit/blob/main/devices/templates.json)):
pick the model and the ESP (original, Seeed XIAO ESP32-C3, ESP32-C3).

* **New device:** a name is suggested; a new API encryption key and OTA
  password are generated and stored in the Device Builder's `secrets.yaml` as
  `<name>_api_key` / `<name>_ota_password`. Flash it once over USB from the
  Device Builder; after that, updates come over the air
* **Device already in Home Assistant without a config:** it keeps its name
  and its API encryption key, which is taken from Home Assistant's ESPHome
  connection to the device (none there: no encryption) and stored as
  `<name>_api_key`. Home Assistant does not know the OTA password, so the
  flow asks for it (leave it empty if the device has none)
* Wi-Fi comes from the shared `wifi_ssid`, `wifi_password` and
  `wifi_ap_password` secrets, which must exist. The integration reads secret
  **names** only, never values, and never overwrites an existing secret

**Template configs follow the templates.** A config made from a template (or a
pasted builder file) is recognised by its first line. Every update rewrites it
from the newest builder file first, keeping its name, secrets and channel, then
compiles and uploads. A **custom** config is never rewritten: updates only build
the new component it pulls through its `ref:`.

## Requirements

* Home Assistant 2026.11 or newer
* The **ESPHome Device Builder add-on**, found by Home Assistant's ESPHome
  integration (Home Assistant OS or Supervised). A standalone Device Builder is
  not supported yet
* For installing updates: each device's config in that Device Builder, for
  example a pasted builder file from
  [tuct/levoit](https://github.com/tuct/levoit/tree/main/devices)
* The `esp_version` text sensor in the device config (the builder files have
  it); it is how the integration reads the installed version
* Optional, for devices without a Device Builder config: the `model` text sensor
  (`type: model`, tuct/levoit after 1.7.0)
* The channel comes from the component's source in the config:

  ```yaml
  external_components:
    - source:
        type: git
        url: https://github.com/tuct/levoit
        ref: stable      # or main
      components: [levoit]
      refresh: always    # fetch on every build; the default (1d) can rebuild an old commit
  ```

## Installation

Not in the default Marketplace catalog yet. Add it as a custom repository:
**Settings → Marketplace → ⋮ → Custom repositories**, enter
`https://github.com/tuct/levoit-esphome-ha`, type *Integration* (needs a
one-time GitHub sign-in). Install it, then add **Levoit ESPHome** under
**Settings → Devices & services**.

## How it works

* Devices: every ESPHome device whose Device Builder config loads `levoit` or
  `philips`, or that has an `esp_version` sensor reporting a component version
  or a `model` sensor reporting a known model (both matched by their state, so
  their names do not matter)
* Model and channel come from the resolved config (`esphome config` in the
  Device Builder). That output contains resolved secrets; the integration keeps
  only the model and the source, and reads each config at most every 6 hours
  or after a build
* Newest versions: the latest release and the `stable` / `main` heads of
  tuct/levoit on GitHub, every 6 hours
* Behind on `stable`: a newer release is out (a build from `main` after that
  release is not behind). Behind on `main`: it runs another commit than the
  head of `main`; a build without a commit in its version (1.7.0 and older) is
  compared by release number. A local `.dirty` build is never offered an update

## Development

Home Assistant does not run on Windows; run the tests on Linux, macOS or in
WSL:

```bash
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```
