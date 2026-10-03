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
| Default speaker | select | | The Sonos group to stream to. Unavailable outside Sonos output, or when no Sonos groups are found. |
| Streaming quality | select | Config | Prioritize connection, Standard, or Prioritize audio quality. |
| Sonos audio delay | select | Config | Min, Med, High or Max. |
| RCA mode | select | Config | Switching or Simultaneous. |
| Restart | button | Config | Reboots the turntable. |

Home Assistant leaves config and diagnostic entities out of its auto-generated
dashboards. The device page lists them in cards of their own.

## Playing the turntable elsewhere

The turntable appears in Home Assistant's media browser under "Victrola Stream". Open
it, pick the turntable, then pick a format:

- **Live (HLS)** — `application/vnd.apple.mpegurl`, for players that accept HLS. Players
  that list only `audio/*` media, such as Sonos speakers and audio-only Cast devices,
  don't show it.
- **Live (MP3)** — `audio/mpeg`. MP3 works with the widest set of players; start here.
- **Live (FLAC, Ogg)** — 24-bit/48 kHz, wrapped as Ogg (`audio/ogg`) rather than a plain
  `.flac` file, for players that take Ogg.

Each format's URL is read from the turntable at the moment you press play, never
cached, because the turntable picks new stream ports on every reconnect. Audio only
flows while a record is playing. In standby there is no stream to connect to — the
media source can't resolve one — until the turntable wakes (see Limitations).

## Automation examples

These use `turntable` as a placeholder device slug; Home Assistant builds your real
entity IDs from your turntable's own name plus each entity's name, so yours will differ.

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

Play the turntable on another media player when it starts streaming. This plays the
turntable's media source, not the Stream URL (MP3) sensor: the media source reads the
URL at play time, while the sensor can still read unknown just after the turntable
wakes from standby.

```yaml
automation:
  - alias: Play the turntable in the kitchen when it starts streaming
    triggers:
      - trigger: state
        entity_id: binary_sensor.turntable_streaming
        to: "on"
    actions:
      - action: media_player.play_media
        target:
          entity_id: media_player.kitchen
        data:
          media_content_id: media-source://victrola_stream/<entry_id>/mp3
          media_content_type: music
```

You don't need to look up `<entry_id>`: in the automation editor, the Play media
action's media picker fills in the whole id when you pick Victrola Stream → your
turntable → Live (MP3).

## Limitations

- **"Platter spinning" watches the motor, not the needle.** It reports the turntable's
  motor sensor, so it's on whenever the platter turns, even if you lift the needle
  without stopping it.
- **Volume is unavailable in Sonos output mode.** Sonos-side volume control is future
  work. Control it from the Sonos app or a Sonos media player entity instead.
- **The turntable sleeps.** After about 10 idle minutes it drops into network standby.
  The API keeps answering, but the stream URL sensors read empty and the media browser
  has nothing to resolve until it wakes.
- **FLAC is Ogg-wrapped.** `audio/ogg`, not `audio/flac`; some players refuse it. MP3
  works with the widest set of players.
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
