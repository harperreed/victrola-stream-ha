# Victrola Stream for Home Assistant

A Home Assistant custom integration for the Victrola Stream turntable. It talks to the
turntable's local HTTP API, tracks the platter and any streaming session, and gives Home
Assistant four things: sensors for the platter and streaming state, controls for volume,
mute, output and the device settings, diagnostics for Wi-Fi signal and power state, and
the turntable's live stream in Home Assistant's media browser so any media player can
play it.

## Supported models

Verified on a Victrola Stream Onyx. Carbon, Pearl and Sapphire run the same firmware
platform and are expected to work, but no one has tested them yet. If you try one, open
an issue and say what worked and what didn't.

Needs Home Assistant 2026.9 or newer.

## Installing

Install through [HACS](https://hacs.xyz/) as a custom repository:

1. HACS → the three-dot menu → **Custom repositories**.
2. Add `https://github.com/harperreed/victrola-stream-ha`, category **Integration**.
3. Install **Victrola Stream** and restart Home Assistant.

This repository isn't published yet. The URL above is where it will live once it is.

## Setting it up

Home Assistant discovers a turntable automatically over mDNS
(`_sues800device._tcp`, advertised with `manufacturer=Victrola`) wherever multicast
reaches it, and offers to set it up. If Home Assistant and the turntable sit on
different VLANs or subnets, multicast usually won't cross that boundary: add the
integration manually instead and enter the turntable's IP address, e.g. `192.0.2.10`.

If that IP address changes later — a new DHCP lease, a move to a different VLAN — open
the device's page and use the three-dot menu's **Reconfigure** option to give it the new
address. The integration keeps the same entities; it just points them at the new host.

## Entities

| Entity | Platform | Category | Notes |
|---|---|---|---|
| Wi-Fi signal | sensor | Diagnostic | Signal strength, in dBm. |
| Power state | sensor | Diagnostic | `Online` or `Network standby`. |
| Stream URL (HLS) | sensor | Diagnostic | Current HLS playlist URL. Empty in standby. |
| Stream URL (MP3) | sensor | Diagnostic | Current MP3 stream URL. Empty in standby. |
| Stream URL (FLAC) | sensor | Diagnostic | Current Ogg-FLAC stream URL. Empty in standby. |
| Platter spinning | binary_sensor | | On while the platter motor turns. |
| Streaming | binary_sensor | | On during a Sonos or UPnP streaming session. Unavailable in Roon or Bluetooth output. |
| Mute | switch | | |
| Autoplay | switch | Config | |
| RCA fixed volume | switch | Config | |
| Volume | number | | 0–100. Unavailable outside UPnP or Bluetooth output. |
| Knob brightness | number | Config | 0–100. |
| RCA delay | number | Config | 0–500 ms. |
| Output | select | | Sonos, UPnP, Roon or Bluetooth. |
| Default speaker | select | | The Sonos group to stream to. Unavailable outside Sonos output. |
| Streaming quality | select | Config | Prioritize connection, Standard, or Prioritize audio quality. |
| Sonos audio delay | select | Config | Min, Med, High or Max. |
| RCA mode | select | Config | Switching or Simultaneous. |
| Restart | button | Config | Reboots the turntable. |

Config and diagnostic entities are hidden from the device's default card; open the
device page to see all of them.

## Playing the turntable elsewhere

The turntable appears in Home Assistant's media browser under "Victrola Stream". Open
it, pick the turntable, then pick a format:

- **Live (HLS)** — `application/vnd.apple.mpegurl`. Works with almost any Home Assistant
  media player.
- **Live (MP3)** — `audio/mpeg`. Also works almost everywhere.
- **Live (FLAC, Ogg)** — 24-bit/48 kHz, but wrapped as Ogg (`audio/ogg`), not a plain
  `.flac` file. Some media players refuse Ogg; try HLS or MP3 if one does.

Each format's URL is read from the turntable at the moment you press play, never
cached, because the turntable picks new stream ports on every reconnect. Audio only
flows while a record is actually playing; in standby the stream carries no audio at
all (see Limitations).

## Automation examples

Turn on a light while the platter spins:

```yaml
automation:
  - alias: Lamp on while the record plays
    triggers:
      - trigger: state
        entity_id: binary_sensor.turntable_platter_spinning
        to: "on"
    actions:
      - action: light.turn_on
        target:
          entity_id: light.turntable_lamp
```

Notify a phone when the turntable starts streaming:

```yaml
automation:
  - alias: Notify when the turntable starts streaming
    triggers:
      - trigger: state
        entity_id: binary_sensor.turntable_streaming
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: The turntable is streaming.
```

## Limitations

- **"Platter spinning" watches the motor, not the needle.** It reports the turntable's
  motor sensor, so it's on whenever the platter turns, even if you lift the needle
  without stopping it.
- **Volume is unavailable in Sonos output mode.** Sonos-side volume control is future
  work. Control it from the Sonos app or a Sonos media player entity instead.
- **The turntable sleeps.** After about 10 idle minutes it drops into network standby.
  The API keeps answering, but the stream URL sensors read empty and the media browser
  has nothing to resolve until it wakes.
- **FLAC is Ogg-wrapped.** `audio/ogg`, not `audio/flac`; some players refuse it. HLS
  and MP3 work with any player.
- **Local only.** Everything happens on your network. No cloud account, no app, no
  telemetry.

## Development

```bash
uv sync                                                # install the dev environment
scripts/check                                          # ruff lint, ruff format check, pytest
VICTROLA_HOST=192.0.2.10 scripts/e2e                   # live suite against a real turntable
scripts/capture_fixtures.py 192.0.2.10 tests/fixtures  # record and sanitize device fixtures
```

`scripts/check` is the canonical check; it must pass before every commit. `scripts/e2e`
and `scripts/capture_fixtures.py` talk only to `$VICTROLA_HOST` (or the host you pass)
on port 80 and the stream URLs that host returns — nothing else on the network.
