# Victrola Stream for Home Assistant — design

- **Date:** 2026-10-03
- **Status:** approved by Doctor Biz: "let's build it. GO GO GO." (2026-10-03)
- **Repo:** `victrola-stream-ha` (local git only; pushing to GitHub as `harperreed/victrola-stream-ha` waits for explicit approval)
- **Device reference:** `../victrola-stream-go/docs/victrola-nsdk-api.md`, `../victrola-stream-go/docs/live-stream-discovery.md`, `../victrola-stream-go/gotchas.md`

## Goal

A simple Home Assistant custom integration for the Victrola Stream turntables, installable
from HACS as a custom repository. It covers Doctor Biz's four uses:

1. **Automate off the record:** know when the platter spins and when the turntable streams.
2. **Control:** volume, mute, output, default speaker, autoplay and the device settings.
3. **Monitor:** Wi-Fi signal, power state, firmware, online/offline.
4. **Listen anywhere:** play the turntable's live stream on any Home Assistant media player.

It's verified on one Victrola Stream Onyx (firmware `0.43.179.0x2aa3460`, MCU
`STM32F030C8_1.11`). The Carbon, Pearl and Sapphire run the same platform and app but
are untested; the README says so.

## Decisions

Answers Doctor Biz gave during brainstorming (2026-10-02 to 2026-10-03), quoted:

| Question | Answer |
|---|---|
| Use cases | "Automate off the record, Control it, Monitor it, Listen anywhere" |
| How to handle the unknowns | "Needle-drop first (Recommended)" |
| Stream URL discovery, after the device-side hunt came up empty | "Descope v1" |
| v1 scope, after the `adchls:serverUrl` nodes turned up | "All of it (Recommended)" |
| Update mechanism | "Push-first (Recommended)" |
| Section 1 (packaging and architecture) | "Looks right" |
| Section 2, revised (entities, media source, config flow) | "Looks right" |
| Section 3 (errors and testing) | "Looks right" |

Standing constraints from the session: no port scans of LAN devices, no fake UPnP
renderer, and no querying Sonos to discover stream URLs.

## Device facts this design relies on

✅ = verified against the live Onyx. 🔧 = from the firmware's `libnsdk_*.so` strings,
read but not exercised. ❓ = still to verify; each ❓ gets a failing test or a live check
before the code that depends on it ships.

| Fact | Status |
|---|---|
| HTTP API on port 80. `GET /api/getData?path=<node>&roles=value` returns `[{"type":T, T:v}]`; `roles=@all` returns the node object with `value`, `type`, `modifiable`, `timestamp` | ✅ |
| `POST /api/setData {"path","role":"value"\|"activate","value"}` answers `true`, `{"value":…}`, `false` or `{"error":…}`; errors arrive with HTTP 200 | ✅ |
| `settings:` writes need the typed shape `{"type":"bool_","bool_":true}`; a bare value can be ignored while the reply still looks like success | ✅ (other session, `upnpEnabled`) |
| `GET /api/getRows?path=…&roles=@all&from=0&to=N&type=structure` returns `{"rows":[…],"rowsCount":N}` | ✅ |
| Event queue: `POST /api/event/modifyQueue {"queueId":"","subscribe":[{"path":P,"type":"itemWithValue"}],"unsubscribe":[]}` returns a JSON string `"{uuid}"`; `GET /api/event/pollQueue?queueId=…&timeout=<seconds>` returns `[]` at timeout or `[{"itemType":"update","path":P,"itemValue":{…},"rowsEvents":[]}]` | ✅ |
| `pollQueue` timeout is in **seconds** (`5` → 5.3 s, `2` → 2.1 s) | ✅ |
| An abandoned queue (left unpolled) expires: `pollQueue` then answers HTTP 400 `Unknown queue id!` within 14 minutes | ✅ |
| What `unsubscribe` does; `rows`-type subscriptions | ❓ |
| Identity: `settings:/system/serialNumber` (equals the mDNS TXT `serial`), `primaryMacAddress`, `manufacturer` = `Victrola`, `productName` = `Victrola Stream`, `settings:/deviceName`, `settings:/version`, `hostlink:hostFirmwareVersion` | ✅ |
| mDNS `_sues800device._tcp` on port 80 with TXT `name`, `serial`, `uuid`, `manufacturer=Victrola`, `ip` | ✅ (captured from `media-tools`) |
| Stream URLs: `adchls:serverUrl` (HLS, `…:8143/pl.m3u8`), `adchls:serverUrl/mp3`, `adchls:serverUrl/flac` (Ogg-FLAC 24/48, `audio/ogg`) | ✅ |
| Stream ports change on every boot (FLAC 38735 → 44323 across a reboot) | ✅ |
| Stream servers answer even when idle but send no audio bytes until a record plays | ✅ |
| An event when a stream URL changes: clears when a session ends, returns (same ports) when one starts | ✅ |
| `hostlink:motorDet` reads `true` while the platter spins and delivers events | ✅ |
| `hostlink:motorDet` goes `false` when the platter stops (a record change can give a quick off/on pair) | ✅ |
| `victrola:isConnectedToSonosGroup` reads `true` during a Sonos session | ✅ |
| It goes `false` exactly 3 minutes after the platter stops | ✅ |
| `victrola:UpnpState` reads `{"pstUpnpState":"notPlaying"}` when idle | ✅ |
| The `UpnpState` value while streaming in UPnP mode | v2 |
| Speakers: `getRows victrola:ui/speakerSelection` rows carry `id`, `type` (`victrolaOutputSonos`), `title`; the default carries `preferred: true` | ✅ |
| Set the default: `activate victrola:ui/setDefaultOutput {"type":…,"id":…}` | ✅ (Go CLI build) |
| Output toggles `settings:/victrola/{sonos,upnp,roon,bluetooth}Enabled` are exclusive; a typed write enabling UPnP disabled Sonos | ✅ |
| Enum options: `forceLowBitrate` = `connectionQuality`/`soundQuality`/`losslessQuality`; `wirelessAudioDelay` (`adchlsLatency`) = `min`/`med`/`high`/`max`; `adchls/dacMode` = `switching`/`simultaneous` | ✅ (read) |
| The typed write shape for enums: confirmed `{"type":"adchlsLatency","adchlsLatency":"max"}` for `wirelessAudioDelay` — the type name matches the enum's own type, not a shared wrapper | ✅ |
| Slider metadata: `lightBrightness` 0–100, `adchls/dacDelay` 0–500 ms | ✅ |
| `player:volume` (0–100) bare-int write returns `true` | ✅ |
| `player:volume` reads 0 in Sonos mode and 14 in UPnP mode | ✅ |
| `player:volume` tracks the Sonos group volume during a session (write 21→22→21 confirmed with read-back and events); reads 0 with no session, so the `getSonosVolume`/`setSonosVolume` actions are unneeded | ✅ |
| `powermanager:target` reads `{"target":"online",…}` | ✅ |
| Reboot via `activate powermanager:goReboot true` | ✅ (Go CLI) |
| `network:info` → `wireless.signalLevel` (dBm) | ✅ |
| Live RSSI events from `network:wirelessRssi` | ❓ |

## Architecture

### Repository layout

```
victrola-stream-ha/
  custom_components/victrola_stream/
    __init__.py        setup/unload; stores the coordinator in entry.runtime_data
    manifest.json
    nsdk.py            async NSDK client, typed values, event queue
    coordinator.py     push-first coordinator and the VictrolaState snapshot
    entity.py          base entity and DeviceInfo
    config_flow.py
    binary_sensor.py  button.py  number.py  select.py  sensor.py  switch.py
    media_source.py
    diagnostics.py
    strings.json  translations/en.json
    brand/icon.png  brand/icon@2x.png  brand/logo.png
  tests/               unit, integration (HA harness) and e2e (real device)
  scripts/check  scripts/e2e
  pyproject.toml       uv-managed dev and test dependencies only
  hacs.json  README.md  LICENSE (MIT)  CLAUDE.md  gotchas.md
  docs/superpowers/specs/  docs/superpowers/plans/
```

### Packaging

- **Domain** `victrola_stream`, one integration per repo under `custom_components/`.
- **manifest.json:** `domain`, `name` "Victrola Stream", `version` "0.1.0", `documentation`
  `https://github.com/harperreed/victrola-stream-ha`, `issue_tracker`
  `https://github.com/harperreed/victrola-stream-ha/issues`, `codeowners` `["@harperreed"]`,
  `config_flow: true`, `integration_type: "device"`, `iot_class: "local_push"`,
  `requirements: []` (aiohttp ships with HA), and
  `zeroconf: [{"type": "_sues800device._tcp.local.", "properties": {"manufacturer": "victrola"}}]`.
  ❓ Verify the property-matcher syntax and value case, and whether a `media_source`
  platform needs `"dependencies": ["media_source"]`.
- **hacs.json:** `{"name": "Victrola Stream", "homeassistant": "2026.9.0"}`. That's the HA
  line we test against (2026.9.4 stable, Python ≥3.14.2).
- **Brand images:** a local `brand/` folder, which HA has supported for custom
  integrations since 2026.3, so no PR to the brands repo is needed.
- **Schemas:** HA core now depends on `probatio==0.11.4` rather than `voluptuous`
  (verified in core's `pyproject.toml` at tag 2026.9.4). ❓ Use whatever import the current
  developer docs show for config-flow schemas.
- **CI** (added with the GitHub push): hassfest, HACS validation and pytest.

### NSDK client (`nsdk.py`)

A small async client on HA's shared aiohttp session (`async_get_clientsession`), ported
from the Go `internal/nsdk` package.

- `NsdkValue`: parses `{"type":T, T:v}`, exposes `as_bool`/`as_int`/`as_str`/raw, and
  treats `{}` or `null` as empty.
- `get_value(path)`, `get_values(paths)` (concurrent), `get_rows(path, start, end)`.
- `set_typed(path, type_, value)` writes `{"type":type_, type_:value}` with role `value`,
  then reads the node back. Anything but the requested value raises `NsdkWriteRejected`.
- `set_value(path, value)` (bare; used for `player:volume`, whose bare write is verified)
  and `activate(path, value)` for actions.
- Success rules: a literal `true` or a `{"value":…}` object is accepted; `false` or an
  `{"error":…}` body is an error. NSDK error bodies become `NsdkError(name, message)`, and
  `invalidPath` gets its own subclass. Transport failures become `NsdkConnectionError`.
- Event queue: `subscribe(subscriptions) -> queue_id`, `poll(queue_id, timeout_s) ->
  list[NsdkEvent]`, `unsubscribe(queue_id, subscriptions)`.
- Timeouts: 10 s for normal requests; for polls, the poll timeout plus 10 s.

### Coordinator (`coordinator.py`)

`VictrolaCoordinator(DataUpdateCoordinator[VictrolaState])` holds one source of truth.

- **Full read** (`_async_update_data`, also the 5-minute safety refresh): concurrent
  `getData` of every state node, plus `getRows victrola:ui/speakerSelection`. It returns a
  `VictrolaState` snapshot: a map of node path to `NsdkValue`, the parsed speaker list, and
  the set of nodes that answered `invalidPath`.
- **Push loop:** after the first successful read, a background task created with
  `entry.async_create_background_task` subscribes every state node (`itemWithValue`). It
  then loops `poll(timeout=25)`, applying each update to a copy of the snapshot and calling
  `async_set_updated_data`. Any poll error logs, backs off (1 s, doubling, capped at 30 s),
  recreates the queue and asks for a full read, so a reboot heals itself and stream URLs
  are always re-read after a reconnect.
- **Unload:** cancel the task and unsubscribe (best effort).
- Entities never hold device state of their own; they read the snapshot.

### Data flow

```
entity action → nsdk write (typed, read back) → device
device change → event queue → coordinator snapshot → every entity
```

## Entities

There's one HA device per turntable. Its name comes from `settings:/deviceName`.

| Platform | Name | Node(s) | Category | Status |
|---|---|---|---|---|
| binary_sensor | Platter spinning (`running`) | `hostlink:motorDet` | — | read ✅, false ❓ |
| binary_sensor | Streaming | Sonos mode: `victrola:isConnectedToSonosGroup`; other modes: unavailable (UPnP streaming state is v2) | — | Sonos ✅, end ✅ |
| number | Volume (0–100) | `player:volume`; always in UPnP/Bluetooth, in Sonos mode only while `isConnectedToSonosGroup` is true | — | UPnP ✅, Bluetooth ❓, Sonos ✅ |
| switch | Mute | `settings:/mediaPlayer/mute` | — | read ✅, typed write ❓ |
| select | Output (Sonos, UPnP, Roon, Bluetooth) | the four `settings:/victrola/*Enabled` toggles | — | ✅ |
| select | Default speaker | `speakerSelection` rows → `setDefaultOutput`; options are the Sonos groups, current = `preferred: true`; unavailable outside Sonos mode | — | ✅ |
| switch | Autoplay | `settings:/victrola/autoplay` | config | read ✅, typed write ❓ |
| number | Knob brightness (0–100) | `settings:/victrola/lightBrightness` | config | read ✅, typed write ❓ |
| select | Streaming quality | `settings:/victrola/forceLowBitrate` | config | enum write ❓ |
| select | Sonos audio delay | `settings:/victrola/wirelessAudioDelay` | config | enum write ❓ |
| select | RCA mode | `settings:/adchls/dacMode` | config | enum write ❓ |
| number | RCA delay (0–500 ms) | `settings:/adchls/dacDelay` | config | typed write ❓ |
| switch | RCA fixed volume | `settings:/adchls/fixedVolume` | config | typed write ❓ |
| button | Restart (`restart`) | `activate powermanager:goReboot true` | config | ✅ |
| sensor | Wi-Fi signal (dBm, `signal_strength`) | `network:info` `wireless.signalLevel`; live from `network:wirelessRssi` if it sends events | diagnostic | ✅ / ❓ |
| sensor | Power state (enum) | `powermanager:target` `.target` | diagnostic | ✅ |
| sensor | Stream URL HLS / MP3 / FLAC | `adchls:serverUrl`, `/mp3`, `/flac` | diagnostic | ✅ |

- **Availability:** online/offline is entity availability. A node that answered
  `invalidPath` at setup gets no entity at all, so other models degrade instead of failing.
- **Device card:** identifiers `{(victrola_stream, serial)}`, connections
  `{(mac, primaryMacAddress)}`, manufacturer, model (`productName`), name, `sw_version`
  (`settings:/version`), `hw_version` (`hostlink:hostFirmwareVersion`), `serial_number`,
  `configuration_url` `http://<host>/webclient/`.
- **Names** come from `strings.json` translation keys with `has_entity_name = True`.

## Media source (`media_source.py`)

The turntable appears in HA's media browser under "Victrola Stream". Each configured
turntable has three playable items: Live (HLS), Live (MP3) and Live (FLAC, Ogg).

- **Resolving** an item reads that format's URL fresh from the device at that moment;
  if the device doesn't answer, resolving fails with a clear error rather than handing
  out a URL that may be stale. It returns the URL with MIME type `application/vnd.apple.mpegurl`, `audio/mpeg` or `audio/ogg`.
- The stream carries audio only while a record plays; that's documented, not hidden.
- ❓ Verify the current `MediaSource` / `BrowseMediaSource` API against HA 2026.9 before
  writing it.

## Config flow (`config_flow.py`)

- **User step:** enter a host. Read `serialNumber`, `manufacturer` and `deviceName`.
  Unreachable → form error `cannot_connect`; manufacturer other than `Victrola` → form
  error `not_victrola`, so a mistyped host can be fixed in place. Unique ID = serial, aborting if already configured. Title = device name.
- **Zeroconf step:** require TXT `manufacturer` = `Victrola`; unique ID = TXT `serial`;
  `_abort_if_unique_id_configured(updates={CONF_HOST: <discovered ip>})`; then a confirm
  step showing the name.
- **Reconfigure step:** a new host whose serial must match the entry (`wrong_device`
  otherwise).
- No options flow; nothing needs tuning.

## Error handling

- **Unreachable device:** entities go unavailable; the push loop backs off and
  resubscribes; reconnecting triggers a full read. `ConfigEntryNotReady` at setup until the
  device answers.
- **NSDK error bodies:** typed errors. `invalidPath` at setup means no entity for that node.
- **Writes:** typed value, then read back. `false`, an error, or an unchanged value raises
  a translated `HomeAssistantError`. No optimistic state.
- **Event queue:** 25 s polls with a 35 s HTTP timeout; any error recreates the queue.
- **IP changes:** zeroconf rediscovery updates the host; otherwise the reconfigure step.
- **Diagnostics:** `async_get_config_entry_diagnostics` returns the snapshot and the
  config entry with serial, MAC, SSID, BSSID and IP addresses redacted.

## Testing

- **Unit** (plain pytest): value parsing, request building and the success/error rules,
  against a local test server replaying payloads captured from the Onyx.
- **Integration** (`pytest-homeassistant-custom-component`, pinned to the release that
  pins HA 2026.9.x; ❓ which one): every config-flow path, setup and unload, entity
  creation and skipping, event application, write paths including rejected writes, and
  media-source browse/resolve. HA's `aioclient_mock` serves recorded device payloads.
- **End-to-end** (`scripts/e2e`, opt-in with `VICTROLA_HOST`, real device, no fakes):
  the config flow creates the entry; entities carry real values; knob brightness goes from
  its current value to one step up and back, confirmed by read-back *and* by the event; all three stream URLs serve
  audio that `ffprobe` decodes while a record plays; the media source resolves a playable
  URL.
- **Live checklist** (needs Doctor Biz at the turntable; recorded in the plan): platter
  `false` transition, Streaming on/off, output-mode change, default-speaker change,
  restart, Sonos-volume actions, typed enum writes.
- **`scripts/check`:** `uv run ruff check`, `uv run ruff format --check`, unit and
  integration tests. This is the canonical check.

## Out of scope for v1 (phase 2)

- Knob double-press and long-press (`victrola:doublePressKnob`/`longPressKnob`) as device
  triggers.
- Standby and wake (`powermanager:goNetworkStandby`/`goOnline`).
- A `media_player` with start/stop (`victrola:startStream`/`stopStream`) and a real
  playing state.
- Music-versus-silence detection from the audio.
- Quickplay.
- Roon zones and Bluetooth outputs (`victrola:roonZones`, `victrola:bluetoothOutputs`) in
  the default-speaker select.
- HA as a UPnP renderer.
- Submission to the HACS default store.

## Risks

- **Firmware updates can rename or drop nodes.** Per-node degradation keeps the
  integration loading; the e2e suite catches regressions on the Onyx.
- **`motorDet` reports the motor, not the needle.** The name says "Platter spinning",
  not "Record playing".
- **Queue lifetime is unknown.** Resubscribe-on-error covers expiry, and the 5-minute full
  read covers missed events.
- **Enum and setting writes are unverified until tested.** Entities whose write shape
  can't be verified ship read-only (as sensors) rather than as controls that silently fail.
- **Only one model has been tested.** The README lists the Onyx as verified and the rest
  as expected to work.
