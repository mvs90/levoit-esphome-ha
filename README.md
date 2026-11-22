# Levoit ESPHome

A Home Assistant integration for air purifiers and humidifiers running the
[`levoit`](https://github.com/tuct/levoit) or `philips` ESPHome components.

It finds every ESPHome device built with those components, links it to its
config in the ESPHome Device Builder, and offers an update when the device's
channel has a newer component version. Installing compiles the config in the
Device Builder and uploads it over the air.

> **Early version.** Part of the
> [firmware update plan](https://github.com/tuct/levoit/blob/main/docs/firmware-updates.md),
> phase 4a.

## What you get

On each purifier's own device page:

| Entity | What it shows / does |
|--------|----------------------|
| **Component firmware** (update) | Installed component version against the newest one on the device's channel; release notes; *Install* compiles and uploads |
| **Compile firmware** (button) | Compiles in the Device Builder without uploading |
| **Component model** | `model:` from the config, e.g. `CORE300S` |
| **Firmware channel** | `stable` (releases), `main` (every merge), `pinned` (another ref or a fork) or `local` |
| **Device Builder config** | The config file the device is built from |

A newer **ESPHome** version is already offered by Home Assistant's own ESPHome
firmware update; this integration adds the component version.

## Requirements

* Home Assistant 2026.11 or newer
* The **ESPHome Device Builder add-on**, found by Home Assistant's ESPHome
  integration (Home Assistant OS or Supervised). A standalone Device Builder is
  not supported yet
* Each device's config in that Device Builder, for example a pasted builder
  file from [tuct/levoit](https://github.com/tuct/levoit/tree/main/devices)
* The `esp_version` text sensor in the device config (the builder files have
  it); it is how the integration reads the installed version
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
  `philips`, or whose `esp_version` sensor reports a component version
* Model and channel come from the resolved config (`esphome config` in the
  Device Builder). That output contains resolved secrets; the integration keeps
  only the model and the source, and reads each config at most every 6 hours
  or after a build
* Newest versions: the latest release and the `stable` / `main` heads of
  tuct/levoit on GitHub, every 6 hours
* A device is behind when it runs another commit than its channel's head; a
  build without a commit in its version (1.7.0 and older) is compared by release
  number; a local `.dirty` build is never offered an update

## Development

Home Assistant does not run on Windows; run the tests on Linux, macOS or in
WSL:

```bash
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```
