# Levoit ESPHome

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/P4P721ETB5)

A Home Assistant integration for air purifiers and humidifiers running the
`levoit` or `philips` ESPHome components of
**[tuct/levoit](https://github.com/tuct/levoit)**: the project that takes
Levoit and Philips purifiers off the cloud, with the components, device
configs and wiring guides.

What it does, in three parts:

### 1. Use and set up your purifiers

A sidebar page with every purifier as a card: power, mode and speed, PM2.5,
AQI and CADR at a glance. Each purifier has a page of its own with its air
quality history and all its settings, grouped instead of one long list.
[More](#use-and-set-up-your-purifiers)

<p>
  <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/overview.png?v=0.6.7" width="49%" alt="The sidebar page: seven purifiers as cards, each with power, mode and speed, PM2.5, AQI and CADR">
  <img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/device-page.png?v=0.6.7" width="49%" alt="The Everest Air's page: power, mode and speed, PM2.5, PM1.0, PM10, AQI and CADR, its group, the 24 hour history and the settings">
</p>

### 2. Run several purifiers as one group

Combine purifiers into a group, for example everything in one room. In
*Auto* the group follows shared air sensors and sets every purifier's speed
by itself: up at once when the air gets worse, down step by step when it
clears. Each group is also one fan entity, so a dashboard, voice or an
automation runs the whole room like one purifier.
[More](#purifier-groups)

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/groups.png?v=0.6.7" width="49%" alt="Purifier groups: a group of two purifiers in Auto at level 3 of 4, and a suggested room">

### 3. Manage and update the devices

It finds every ESPHome device built with those components, links it to its
config in the ESPHome Device Builder, and offers an update when the device's
channel has a newer component version. Installing compiles the config in the
Device Builder and uploads it over the air. *Add device* makes the config for
a new purifier.
[More](#manage-and-update-the-devices)

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/panel-updates.png?v=0.6.7" width="49%" alt="Updates and config: every device with its channel, installed and latest version, and Compile and Update">

> **Early version.** Part of the
> [firmware update plan](https://github.com/tuct/levoit/blob/main/docs/firmware-updates.md).


## Use and set up your purifiers

Turn on **Settings → Devices & services → Levoit ESPHome → ⚙ (Configure) →
Show in the sidebar** for a *Levoit ESPHome* page, visible to admins only. It
has three tabs and updates live. It is a plain web component served by the
integration; nothing is loaded from outside Home Assistant. After updating the
integration, reload the browser once to get the new page.

### Devices tab

Every purifier as a card, for using them. A line on top counts the purifiers
running, off and offline, and names the one with the worst air. Each card has a
small outline of the model, an air quality dot, power, the mode and the speed,
PM2.5, AQI (the level 1–4 and its word, *1 Very good* to *4 Poor*) and the
current CADR, the filter left, and the time left when a timer runs. Chips under
the model show an update that is out and the purifier's group (tinted while
the group runs it). Offline cards keep their controls, greyed out. Click a
card for the device's page.

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/overview.png?v=0.6.7" width="720" alt="Devices: purifiers as cards with power, mode and speed, PM2.5, AQI and CADR">

### Device page

On top, power, mode and speed with PM2.5, AQI and CADR (the Eleva 300X also
shows its AQI index, 0–500). Below, the **history** of the last 24 hours or
7 days from Home Assistant's statistics, in one chart: PM2.5 as an area
(left axis), CADR as a dashed line (right axis) and the air quality level as a
coloured band under it; the legend chips switch each one on and off. A
purifier in a group shows a banner with the group's status and what a change
here does.

Then the settings, grouped instead of one long list: *Automatic* (auto mode,
room size only when it applies), *Sleep* (the Vital 200S custom profile: quick
clean, sleep, then daytime mode), *Quiet period* (Eleva 300X, start and end as
times), *Timer* (quick picks and the time left), *Display & panel*, *Filter*
(life %, lifetime, reset) and *Info*. For the Core 200S / 300S / 400S / 600S,
Vital 100S / 200S, Everest Air and Eleva 300X; other models link to Home
Assistant's device page. It needs no Device Builder config: the settings are
found by their entity names, as the tuct/levoit configs name them (or as the
device's config does, when there is one).

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/device-page.png?v=0.6.7" width="720" alt="A device page: power, mode and speed, PM2.5, AQI and CADR, the 24 hour history in one chart, and the settings">

## Purifier groups

Run 2 or more purifiers together from shared air sensors, for example
everything in one room. Groups run in the integration, so they keep working
with the page closed and after a restart.

* **The level:** the worst of the group's sensors, on the group's thresholds,
  sets a level from 1 up to the group's max speed. It goes up at once and down
  one step per hold time (2 minutes); a fast rise in PM2.5 jumps straight to
  max speed.
* **The purifiers** switch to Manual at their own speed for that level. A
  3-speed model shares levels, so the top level is always its fastest. The
  Everest Air counts its Turbo as speed 4, so the top level runs it in Turbo.
  *Up to* holds one lower, for example a loud one up to speed 2 (or the
  Everest Air up to 3: no Turbo).
* **Letting go:** once the air is clean, the group is switched off or deleted,
  or a purifier leaves it, the group sends nothing: each keeps running as it is.
* **By hand:** if someone changes a purifier, the group leaves that one alone
  for 30 minutes.
* **Manual:** one speed for all its purifiers instead of following the sensors.

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/groups.png?v=0.6.7" width="720" alt="Purifier groups: each group with its level, reason, sensors and purifiers">

The editor picks the sensors from the purifiers and takes others from Home
Assistant, sets thresholds, max speed, hold time and the speed limit per
purifier, and shows live what the group would do right now. Rooms in Home
Assistant with 2 or more purifiers are suggested as groups.

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/group-editor.png?v=0.6.7" width="720" alt="The group editor: purifiers, sensors, thresholds, the speed each purifier runs per level, and what the group would do now">

Each group gets a device of its name, for dashboards, voice and automations:

| Entity | What it shows / does |
|--------|----------------------|
| **The group** (fan) | The whole group like one purifier: on / off is *Control*, preset *Auto* or *Manual*, and its 4 speeds set the level for all purifiers (Manual, up to the group's max speed) |
| **Control** (switch) | Off: the group leaves its purifiers alone |
| **Level** (sensor) | 0–4, the level the group runs at, with the reason |
| **Air quality** (sensor) | 0–4, the worst sensor on the group's thresholds (0 below level 1); also in Manual or with the group off |
| **Active** (binary sensor) | On while the group runs its purifiers at a level above 0 |

## Manage and update the devices

Firmware updates for every purifier, in Home Assistant's *Updates* and on
the sidebar page's *Updates & config* tab, and *Add device* for new ones.

### Updates & config tab

The sidebar page's third tab has:

* every device: model, ESP / config type, channel, installed → latest
  component version, filter %, ESPHome version, status and the last build
* the latest releases on top, with **Update all** (one device after the other)
* **Compile** and **Compile and upload** (*Update* when one is out), with the
  result per device, and the output of the last build under **Log**
* the channel of a device without a config or with a template config
* configs made by *Add device* that are **not flashed yet**, with what to do
  next; they can be compiled, but not uploaded until the first USB flash
* links to each device's page, the Device Builder and Add device; *check now*
  reads the latest versions from GitHub without waiting for the 6 hours

<img src="https://raw.githubusercontent.com/tuct/levoit-esphome-ha/main/images/panel-updates.png?v=0.6.7" width="720" alt="Updates and config: every device with model, channel, installed and latest version, and Compile, Update and Log">

### Extra ESP or original ESP

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

### Supported models

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

### Entities per purifier

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

### Add device

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

### How it works

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

#### How an update reaches the purifier

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

## Development

Home Assistant does not run on Windows; run the tests on Linux, macOS or in
WSL:

```bash
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```

The README screenshots come from a running Home Assistant with the sidebar
page on, through [`scripts/screenshots.py`](scripts/screenshots.py) (headless
Edge or Chrome, with a long-lived access token of an admin):

```bash
pip install playwright
HA_URL=http://homeassistant.local:8123 HA_TOKEN=<token> python scripts/screenshots.py
```

It saves `overview.png`, `device-page.png`, `groups.png`, `group-editor.png` and
`panel-updates.png` to `images/`. `--device` and `--group` pick which device and
group, `--only overview groups` takes some, `--dark` uses the dark theme,
`--sidebar` keeps Home Assistant's sidebar and `--scale 2` makes them
sharper.

### Encrypted native OTA

Template refreshes preserve the native ESPHome OTA encryption key and API
key, whether inline or referenced by `!secret`. The integration inspects the
YAML without loading packages or looking up secret values. It supports a single
native OTA transport on a standalone template tracking upstream Main or Stable.
If a marked template uses packages, an unsupported transport or a pinned/forked
source, the refresh stops before writing or building. Remove the template marker
to maintain that file as a custom config. Use a Device Builder version that
supports native OTA encryption for an encrypted device.

### LV600S support on the owner test branch

The LV600S page maps native ESPHome entities by their reported names or the
resolved device config. The fallback names cover English device examples and
the German owner profile, including Tank Removed, Water Tank Empty, MCU
Connection, MCU Fault and Timer Remaining.

The timer presets work as soon as the MCU reports fresh status. The page
shows the confirmed duration and remaining time separately from the command. It blocks start when an available tank, water, fault or MCU
diagnostic rules it out.
The power-off control remains available while power is reported on. Auto in the
panel selects the existing target-humidity mode. Auto (Original) and Unknown
appear only under the reported device status.

Home Assistant also exposes a `humidifier` entity on the linked Levoit device.
It uses the existing ESPHome power, mode, humidity and target entities. The
underlying mode select can be hidden from the Home Assistant interface while
remaining available to existing automations.

**English.** The LV600S card shows the tank state next to the model, in the
same position as the filter indicator on purifiers. A drop shows whether water
is available or empty. If the tank is missing, a tank icon replaces the water
status. The card offers three mist presets and shows the current warm mist
level beside its icon. Selecting that level opens Off and levels 1–3 to the
right. On narrow cards, the mode selector is hidden until the warm mist choice
is made or the picker is closed. Choosing a mist preset starts the unit if
needed and waits for Manual before sending the level. A mode selected in
standby starts the device and the card follows its confirmed power, mode and
mist states. The detail header shows mist and warm mist to the
right of the operating mode when space allows. Below the 24-hour or 7-day
history, the timer uses the purifier's presets and shows the remaining time
with a progress bar when the start is known. Configuration contains the
target humidity and display controls. The history shows humidity, temperature
and both device-reported mist settings, with gaps for unavailable readings.

**Deutsch.** Die LV600S-Karte zeigt den Tankstatus neben der Modellbezeichnung
an derselben Stelle wie die Filteranzeige der Luftreiniger. Ein Tropfen zeigt
„Wasser vorhanden“ oder „Wasser leer“. Fehlt der Tank, erscheint das
Tank-Symbol mit „Tank fehlt“. Die Karte zeigt drei Nebelstufen und die aktuelle
Warmnebelstufe mit Symbol. Antippen klappt „Aus“ und die Stufen 1–3 nach rechts
auf. Auf schmalen Karten erscheint die Moduswahl wieder, sobald die Stufe
gewählt oder die Auswahl geschlossen wurde. Bei Wahl einer Nebelstufe startet
das Gerät bei Bedarf und bestätigt zuerst **Manuell**. Bei einer Moduswahl aus
dem Standby aktualisiert die Karte Einschaltzustand, Modus und Nebelstufe anhand
der bestätigten Gerätewerte.
**Auto** regelt auf die eingestellte Zielfeuchte. **Auto (Original)** und
**Unbekannt** erscheinen als gemeldeter Modus im Gerätestatus.
Bei genügend Platz stehen Nebel- und Warmnebelstufen rechts neben der
Moduswahl. Der Verlauf zeigt Luftfeuchtigkeit, Temperatur und beide
gemeldeten Stufen über 24 Stunden oder 7 Tage. Fehlende Messwerte erscheinen
als Lücken. Der Timer darunter nutzt dieselben Zeitvorgaben wie die
Luftreiniger und zeigt bei bekanntem Timerstart einen Fortschrittsbalken.
Zielfeuchte und Display stehen unter Konfiguration.


With the tested `1.2.09-target-preset-startup` firmware, the ESPHome mist, warm
mist and timer numbers allow presets in standby. The timer card shows the
queued duration and starts counting at power-on. Setting Timer (min) to zero
cancels a queued or running timer. With no active timer, both formatted timer
sensors report `Off` once the MCU status arrives. Active mist uses a blue
`mdi:scent` and active warmth an orange `mdi:heat-wave`. Their off icons are
grey. The remaining entity defaults are in the
[firmware guide](https://github.com/mvs90/levoit/blob/codex/owner-test/devices/levoit-lv600s/README.md#controls).

Mit der getesteten Firmware `1.2.09-target-preset-startup` lassen sich Nebel,
Warmnebel und der Timer über die ESPHome-Zahlen im Standby vormerken. Auf der
Timerkarte steht bis zum Einschalten die vorgemerkte Dauer. `0` löscht einen
vorgemerkten oder laufenden Timer. Ohne aktiven Timer zeigen beide Textsensoren
nach der ersten MCU-Rückmeldung `Off`. Bei aktivem Nebel erscheint
`mdi:scent` blau, bei aktiver Wärme `mdi:heat-wave` orange. Die Aus-Symbole
sind grau.

On the owner's LV600S with firmware `1.2.06-mist-controls`, Home Assistant
confirmed the switch from Auto to Manual and the subsequent mist level.

The test branch recognises the LV600S through its existing ESPHome entry. The
Add Device catalogue reads upstream. To reproduce the tested configuration, use
the existing custom Device Builder profile from the
[owner's secure firmware repository](https://github.com/mvs90/levoit-lv600s-local/tree/codex/tuct-alignment).

### Local acceptance on three EU devices

On 25 November 2026, Home Assistant 2026.11.3 ran integration `0.6.7` from code
commit `45b4019ec185d972fc8140c13de89f8abe60890a`. All three devices were online
and supported. The integration detected each custom configuration as local,
and the ESPHome Device Builder successfully compiled all three through the
integration.

| Device | Firmware | Mapped ESPHome entities | Confirmed in Home Assistant |
|---|---|---:|---|
| Core 600S | `1.0.09-tuct-review` | 22 | Power, manual speed, display and timer |
| Vital 100S | `1.0.06-tuct-review` | 24 | Power, manual 50% and 75%, display and timer |
| LV600S | `1.2.02-tuct-review` | 20 | Humidity and temperature, tank/water and MCU status, power, mist/warm level, humidity target, operating modes, display and timer |

For the LV600S follow-up, the time from a Home Assistant command to the matching
Home Assistant state event was 1.00–1.12 seconds for mist, its app scale and
warm level. The change is in the owner firmware profile. The integration uses
the same native ESPHome entities and device entries. Full device findings and
hardware work are recorded in the
[firmware fork's verification report](https://github.com/mvs90/levoit/blob/codex/owner-test/docs/esphome-devices/owner-test.md).

The release review adds protection against matching an auxiliary ESPHome fan on
an LV600S as a purifier or group member. The existing purifier matching rules
and grouped controls remain available for purifier models. The separate
[`codex/lv600s-support` branch](https://github.com/mvs90/levoit-esphome-ha/tree/codex/lv600s-support)
applies the LV600S changes on upstream 0.6.8. The owner's live verification was
on 0.6.7 and did not use that newer build.
[Dependency and verification notes](https://github.com/mvs90/levoit/blob/codex/owner-test/devices/levoit-lv600s/RELEASE-REVIEW.md)
