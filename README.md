# Levoit ESPHome

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/P4P721ETB5)

A Home Assistant integration for air purifiers and humidifiers running the
`levoit` or `philips` ESPHome components of
**[tuct/levoit](https://github.com/tuct/levoit)**: the project that takes
Levoit and Philips purifiers off the cloud, with the components, device
configs and wiring guides.

It finds every ESPHome device built with those components, links it to its
config in the ESPHome Device Builder, and offers an update when the device's
channel has a newer component version. Installing compiles the config in the
Device Builder and uploads it over the air.

![The Levoit ESPHome sidebar page: each device with model, ESP, channel, installed and latest version, filter %, status, Update, Compile and Compile & upload](https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/panel.png)

> **Early version.** Part of the
> [firmware update plan](https://github.com/tuct/levoit/blob/main/docs/firmware-updates.md).

## Use cases

Most of these purifiers have an ESP32 for Wi-Fi and a separate MCU that runs
the purifier, talking over UART. ESPHome can run on that ESP in two ways:

| | **Extra ESP** (recommended) | **Original ESP** |
|---|---|---|
| What | A small ESP of your own, wired to the MCU's UART; the original ESP stays on the board, held in reset | The purifier's own ESP, flashed with ESPHome |
| Hardware | A [Seeed XIAO ESP32-C3](https://www.seeedstudio.com/Seeed-XIAO-ESP32C3-p-5431.html) or [XIAO ESP32-S3](https://www.seeedstudio.com/XIAO-ESP32S3-p-5627.html) (or any ESP32 ESPHome supports) and a few wires: power, GND, RX, TX, and the original ESP's EN to GND | None |
| Back to stock | Remove the wires: the stock firmware was never touched | Restore a backup of the stock flash over its UART pads |
| First flash | Over USB from the Device Builder, before you wire it in | Over the board's UART pads, usually with the purifier open |
| Risk | Low: a bad build only hits your ESP, which you can reflash over USB at your desk | A bad build can leave the purifier offline until you open it again |
| Locked modules | Works with every model, also those whose stock ESP can't be flashed (Philips AC0650: secure boot) | Only modules without secure boot |

**Why extra:** the purifier's stock firmware stays intact, and a broken build
is never more than a USB cable away from fixed. The XIAO boards are small
enough to fit inside many of these purifiers (the device guides say where).

### Extra ESP: install it and keep it updated

1. *Add device* → **New device** → the model → **Seeed XIAO ESP32-C3** or
   **Seeed XIAO ESP32-S3**. For another board pick **Other ESP**: any ESPHome
   board name and your own RX / TX pins.
2. The integration makes the Device Builder config: name, API key and OTA
   password generated, Wi-Fi from your secrets.
3. Flash it once over USB from the Device Builder (the config → **Install** →
   **Plug into this computer**), then wire it in (see the model's guide in
   [tuct/levoit/devices](https://github.com/tuct/levoit/tree/main/devices)).
   Until then the sidebar page lists it as *Not flashed yet*. Once it is on
   your Wi-Fi, the integration adds it to Home Assistant's ESPHome
   integration by itself: no *discovered device* to confirm.
4. From then on, every new component version shows up in **Settings →
   Updates** and installs over the air.

### Original ESP, already flashed: keep it updated

Flashed the purifier's own ESP with the `levoit` component already? *Add
device* → **Device already in Home Assistant** → the model → **Original ESP**
gives it a Device Builder config. It keeps its name and API key (Home Assistant
keeps the device), and updates come over the air like for any other device.

<details>
<summary><b>Walkthrough:</b> a Core 400S on its original ESP, from 1.3.1 to 1.7.2</summary>

1. *Add device* → **Device already in Home Assistant, without a config**

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-01-menu.png" width="420" alt="Add device: New device, or Device already in Home Assistant without a config">

2. Pick the device. Its config gets the device's own name and API key

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-02-device.png" width="420" alt="Existing device: Levoit-Core400S">

3. The model: asked here because firmware 1.3.1 has no `model` sensor yet

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-03-model.png" width="420" alt="Model: Levoit Core 400S">

4. **Original ESP**

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-04-esp.png" width="420" alt="ESP: Original ESP, Seeed XIAO ESP32-S3, Seeed XIAO ESP32-C3 or Other ESP">

5. Channel, and the OTA password the device was built with (the API key comes from Home Assistant)

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-05-details.png" width="420" alt="Update channel stable, OTA password entered; the API key is stored as levoit_core400s_api_key">

6. The config is in the Device Builder

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-06-done.png" width="420" alt="Success: config levoit-core400s.yaml created">

7. The sidebar page lists it as **Original ESP** with an update from 1.3.1

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-07-update-available.png" width="720" alt="Core 400S, Original ESP, 1.3.1, Update available">

8. **Update** asks first

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-08-confirm.png" width="560" alt="Compile Levoit-Core400S in the ESPHome Device Builder and upload it over the air?">

9. It compiles in the Device Builder …

   <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-09-building.png" width="720" alt="Core 400S building">

10. … uploads over the air (ESPHome 2026.5.3 on the device, 2026.11.0 in the Device Builder) …

    <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-10-uploading.png" width="720" alt="Core 400S uploading, ESPHome 2026.5.3, builder 2026.11.0">

11. … and the purifier runs 1.7.2 and ESPHome 2026.11.0

    <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/original-esp-11-up-to-date.png" width="720" alt="Core 400S, 1.7.2, up to date, uploaded 11:41 PM">

</details>

### Already running, but no config in the Device Builder

A purifier that runs the `levoit` or `philips` firmware already (extra or
original ESP), but whose config is not in this Device Builder: flashed from a
PC with the ESPHome CLI, from another Device Builder, or the config is lost.

The integration finds it anyway, by its `esp_version` (or `model`) sensor: it
shows on the sidebar page with **No config**, and its update entity says when a
new version is out, but cannot install it yet. To onboard it:

1. *Add device* → **Device already in Home Assistant, without a config** →
   pick the device. (**Add config** on its row of the sidebar page opens the
   integration page, where *Add device* is.)
2. **Model:** skipped when the device reports it; firmware older than 1.7.1
   has no `model` sensor, so pick it.
3. **ESP:** the template that matches its hardware (XIAO ESP32-C3, XIAO
   ESP32-S3, original ESP), or **Other ESP** with its board and the RX / TX
   pins it uses now. **They must match how the device is wired**: the next
   update flashes this config. With wrong pins the ESP still starts and stays
   on Wi-Fi, but can't talk to the purifier; fix the pins and update again,
   over the air. With a wrong board the new firmware may not start at all,
   and then only a USB reflash helps. If unsure, take board and pins from the
   config it was built with.
4. **Channel**, and its **OTA password** if it has one: Home Assistant does
   not know it, and the update is uploaded with it. Leave it empty if the
   device has none.

The config keeps the device's **name**, so Home Assistant keeps the device and
its history, and its **API encryption key**, taken from Home Assistant's
connection to the device and stored as `<name>_api_key` in `secrets.yaml`.
Wi-Fi comes from the `wifi_ssid` / `wifi_password` / `wifi_ap_password`
secrets, which must exist. The device moves from *No config* to *Update
available*; the first update builds the new config and installs it over the air.

Have the old config at hand and want to keep it as it is? Paste it into the
Device Builder instead (under the device's name). The integration picks it up
as a **custom** config; a pasted builder file of tuct/levoit counts as a
template.

## Devices

The templates *Add device* offers per model (✓). **Other ESP** works for every
model, with your board and pins.

| Model | XIAO ESP32-C3 | XIAO ESP32-S3 | Original ESP: updates through this integration |
|---|---|---|---|
| Levoit Core 200S | ✓ | ✓ | not tested yet |
| Levoit Core 300S | ✓ | ✓ | not tested yet |
| Levoit Core 400S | ✓ | ✓ | **works**: 1.3.1 → 1.7.2 ([walkthrough](#original-esp-already-flashed-keep-it-updated)) |
| Levoit Core 600S | ✓ | ✓ | not tested yet |
| Levoit Eleva 300X | | ✓ | not tested yet (stock ESP32-C3) |
| Levoit Everest Air | ✓ | ✓ | not tested yet |
| Levoit Superior 6000S | | ✓ | not tested yet |
| Levoit Vital 100S | ✓ | ✓ | not tested yet (stock ESP32-C3) |
| Levoit Vital 200S | ✓ | ✓ | not tested yet (stock ESP32-C3) |
| Philips 600 series (AC0650) | ESP32-C3 template | ✓ | not possible: secure boot |
| Philips 900 series (AC0950) | ✓ | ✓ | |

> **Running the `levoit` firmware on the original ESP of one of these?**
> Add it with *Add device* → *Device already in Home Assistant*, install an
> update, and [tell us how it went](https://github.com/tuct/levoit-esphome-ha/issues/new?title=Original%20ESP%3A%20%3Cmodel%3E):
> the model, and whether the update went through. Each report moves a model
> in this table from *not tested yet* to *works*.

## What you get

Per purifier, on a device of the same name (its *Visit* link opens the ESPHome Device Builder); Home Assistant lists the purifier's
ESPHome device under *Linked devices* (same MAC address). Since Home Assistant
2026.8 an integration cannot add entities to another integration's device.

Devices made with *Add device* sit under their own entry, the others under
*Devices that don't belong to a sub-entry*:

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/integration-page.png" width="640" alt="The integration page: devices with a Device Builder config under their Add device entry, the others below">

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
| **Config type** | `original` / `xiao_c3` / `c3` / `s3`: made from a template; `custom`: your own config |

A newer **ESPHome** version is already offered by Home Assistant's own ESPHome
firmware update; this integration adds the component version.

Component updates show in **Settings → Updates** under *Levoit ESPHome*, like
other firmware updates: install them one by one or with *Update all*. A device
without a Device Builder config is not listed there, as there is nothing to
install yet.

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/updates-page.png" width="560" alt="Settings, Updates: the Levoit ESPHome card with Update all and four purifiers on component 1.7.2, one installing">

Each update shows the installed and the latest version, with the release notes
(stable) or a link to the new commits (main):

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/update-dialog.png" width="380" alt="The Component firmware update of a purifier: installed 1.3.0, latest 1.7.2, with the release notes, installing">

## Sidebar page

Turn on **Settings → Devices & services → Levoit ESPHome → ⚙ (Configure) →
Show in the sidebar** for a *Levoit ESPHome* page, visible to admins only:

* every device: model, ESP / config type, channel, installed and latest
  component version, filter %, ESPHome version, status and the last build
* **Compile** and **Compile and upload** (*Update* when one is out), with the
  result per device, and the output of the last build under **Log**
* the channel of a device without a config or with a template config
* configs made by *Add device* that are **not flashed yet**, with what to do
  next; they can be compiled, but not uploaded until the first USB flash
* **a page per device**: click its name. On top, power, mode and speed,
  with the air quality. Below, the settings grouped instead of one long
  list: *Automatic* (auto mode, room size only when it applies),
  *Sleep* (the Vital 200S custom profile: quick clean, sleep, then daytime
  mode), *Quiet period* (Eleva 300X, start and end as times), *Timer* (quick
  picks and the time left), *Display & panel*, *Filter* (life %, lifetime,
  reset) and *Info*. For the Core 200S / 300S / 400S / 600S, Vital 100S /
  200S, Everest Air and Eleva 300X; other models link to Home Assistant's
  device page. It needs no Device Builder config: the settings are found by
  their entity names, as the tuct/levoit configs name them (or as the
  device's config does, when there is one)
* links to each device, the Device Builder and Add device; *check now* reads
  the latest versions from GitHub without waiting for the 6 hours

The page updates live. It is a plain web component served by the integration;
nothing is loaded from outside Home Assistant. After updating the integration,
reload the browser once to get the new page.

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/panel-updates.png" width="720" alt="The sidebar page with five devices: three with an update, one XIAO ESP32-S3 just uploaded and up to date, one without a Device Builder config">


## Add device

**Settings → Devices & services → Levoit ESPHome → Add device** makes a Device
Builder config from a template of tuct/levoit
([`devices/templates.json`](https://github.com/tuct/levoit/blob/main/devices/templates.json)):
pick the model and the ESP (original, Seeed XIAO ESP32-C3, ESP32-C3, Seeed XIAO ESP32-S3),
or **Other ESP** for a board or pins without a template: enter the ESPHome board
name (e.g. `seeed_xiao_esp32s3`, `esp32dev`, `esp32-c6-devkitc-1`) and the RX / TX
pins, and the config is made from the model's builder file with those.

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/add-device-model.png" width="420" alt="Add device: pick the model">

* **New device:** a name is suggested; a new API encryption key and OTA
  password are generated and stored in the Device Builder's `secrets.yaml` as
  `<name>_api_key` / `<name>_ota_password`. Flash it once over USB from the
  Device Builder; after that, updates come over the air. As soon as the
  flashed ESP is on the network (every 30 s it looks for `<name>.local`), the
  integration adds it to the ESPHome integration with the key from the Device
  Builder, so there is no discovered device to confirm. If the ESP needs
  input it cannot give (a different key, a name clash), it is left to Home
  Assistant's usual discovery
* **Device already in Home Assistant without a config:** it keeps its name
  and its API encryption key, which is taken from Home Assistant's ESPHome
  connection to the device (none there: no encryption) and stored as
  `<name>_api_key`. Home Assistant does not know the OTA password, so the
  flow asks for it (leave it empty if the device has none)
* Wi-Fi comes from the shared `wifi_ssid`, `wifi_password` and
  `wifi_ap_password` secrets, which must exist. The integration reads secret
  **names** only, never values, and never overwrites an existing secret

**Template configs follow the templates.** A config made from a template (or a
pasted builder file) is recognised by its first line,
`# levoit-esphome-ha: template=...`. Every update rewrites it from the newest
builder file first, keeping its name, secrets and channel, then compiles and
uploads. The header under that line says so. **To customise such a config,
delete its first line first**: otherwise the next update overwrites your
changes. Without it the config is **custom**, like one made with *Other ESP*:
it is never rewritten, and updates only build the newer component it pulls
through its `ref:`.

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
  their names do not matter). A device found once stays listed while
  it is offline (*Offline* on the sidebar page, its entities unavailable) and
  is back as soon as it reports again. One that is gone for good can be
  deleted on its device page (*⋮ → Delete*), if it has no Device Builder
  config
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

### How an update reaches the purifier

Everything runs on your Home Assistant host; the purifier only receives the
finished firmware over Wi-Fi.

1. **Config** (template configs only): the integration rewrites the config in
   the Device Builder from the newest builder file, through the Device
   Builder's API, keeping the name, secrets and channel. A custom config is
   left as it is.
2. **Compile:** the integration asks the Device Builder (the ESPHome add-on) to
   compile the config. It fetches the component from GitHub at the config's
   `ref:` (`stable` or `main`) and builds the firmware on the Home Assistant
   host. The first build takes a few minutes; later ones are faster. If the
   compile fails, nothing is uploaded.
3. **Upload over Wi-Fi:** the Device Builder connects to the purifier's ESP
   with ESPHome's own OTA protocol (TCP port 3232), finds it by its name
   (`<name>.local`, mDNS), authenticates with the OTA password from
   `secrets.yaml` (`<name>_ota_password`), and sends the firmware. The ESP
   writes it into its **second app partition** while the current firmware keeps
   running, checks it (SHA-256), switches the boot partition to it and restarts.
   A connection that drops halfway leaves the old firmware running.
4. **Back online:** the ESP reconnects to Wi-Fi and to Home Assistant (with its
   API key), and reports the new version through its `esp_version` sensor. The
   update entity shows *Up to date*, the sidebar page *Uploaded HH:MM*.

What the upload needs, and what goes wrong otherwise:

| Needed | If not |
|--------|--------|
| The Home Assistant host reaches the ESP on TCP 3232 (same network, or routed without a firewall in between) | *Upload failed*; the device keeps its firmware |
| `<name>.local` resolves from the host (mDNS). Across VLANs or subnets mDNS often doesn't pass | *Upload failed*. Make mDNS pass (a reflector), or give the device a fixed address in a custom config (`wifi: use_address:`) |
| The OTA password in `secrets.yaml` matches the one the device was built with | *Upload failed*; fix the secret in the Device Builder (*Secrets*) and update again |
| The new firmware starts on this hardware (right board) | The ESP doesn't come back and needs a USB reflash. The configs don't enable ESPHome's `safe_mode`, so there is no automatic fallback |

The Device Builder streams the compile and upload output to the integration and
keeps none of it itself. The integration keeps the last 400 lines of each
device's last build: **Log** on the sidebar page shows them, also while a build
runs. When a build fails, its error message names the reason (the last error
line), and the last 40 lines go into Home Assistant's log (*Settings → System →
Logs*).

## Development

Home Assistant does not run on Windows; run the tests on Linux, macOS or in
WSL:

```bash
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```
