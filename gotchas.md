# victrola-stream-ha — gotchas

Distilled traps for anyone (human or agent) working on this integration. Device API
reference: `../victrola-stream-go/docs/victrola-nsdk-api.md` and
`../victrola-stream-go/docs/live-stream-discovery.md`.

## Device API

- **Write settings with typed values, then read them back.** A bare `true` written to
  `settings:/victrola/upnpEnabled` came back as a response object whose value was still
  `false`. The webclient's shape `{"type":"bool_","bool_":true}` took effect. A response
  object alone does not prove a write worked.
- **`pollQueue` timeout is in seconds.** `timeout=5` returned `[]` after 5.3 s and
  `timeout=2` after 2.1 s. The webclient's `timeout=1500` holds for up to 25 minutes and
  returns early on any event. `modifyQueue` with `"queueId":""` returns a server-made
  JSON string like `"{uuid}"`; pass it back as-is (URL-encoded).
- **Stream ports change on every boot.** Read the URLs from `adchls:serverUrl`,
  `adchls:serverUrl/mp3` and `adchls:serverUrl/flac`; never cache a port across a
  reconnect. The FLAC stream is Ogg-wrapped (`audio/ogg`), 24-bit/48 kHz.
- **Vinyl state is not in the player.** `player:player/data/value` stays empty while a
  record plays. Use `hostlink:motorDet` (platter motor) and
  `victrola:isConnectedToSonosGroup` (streaming session) instead.
- **Role roots can't be listed.** `getRows` on `victrola:`, `player:`, `adchls:` returns
  `invalidPath`; `settings:/` can be walked. Live node names came from the firmware's
  `libnsdk_*.so` strings.
- **A missing node answers HTTP 500, not 200.** `getData` on an unknown path (e.g.
  `settings:/victrola/doesNotExist`) returns HTTP 500 with the `invalidPath` error body,
  not a 200 as older docs implied. `NsdkClient` checks every reply for an NSDK
  `{"error": {...}}` body regardless of status, mapping a name ending in `invalidPath` to
  `NsdkInvalidPath`; a non-200 reply with no error body becomes `NsdkConnectionError`.
- **An idle device drops to network standby, and its stream URLs read empty.** After
  about 10 idle minutes (`settings:/system/maxIdleTime` = 600), `powermanager:target`
  reads `networkStandby` (reason `idleTimer`) and every `adchls:serverUrl*` node reads
  `""`, as in `tests/fixtures/get_data.json`. The API still answers. Treat an empty URL
  as "no stream right now", not an error. How the device wakes is still to be checked
  live.

## Working with Doctor Biz

- **No port scans.** Don't port-scan devices on the LAN. Use protocol discovery (SSDP,
  mDNS, the device's own API) or ask Doctor Biz for a capture from `media-tools`, which
  sits on the device VLAN. This Mac can't reach that VLAN by multicast.
- **Ask before theorizing about state changes.** During live sessions Doctor Biz is
  changing the device too. When a value changes and we didn't cause it, ask "did you
  change X?" before building a theory on it. (The "UPnP mode falls back to Sonos" theory
  was just Doctor Biz flipping it back.)
