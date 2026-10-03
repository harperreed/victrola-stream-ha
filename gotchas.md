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
- **The platter motor stops before the Sonos session does.** `hostlink:motorDet` goes
  `false` when the platter stops (a record change can produce a quick off/on pair). The
  session itself ends exactly 3 minutes later: `victrola:isConnectedToSonosGroup` goes
  `false` and all three `adchls:serverUrl*` nodes clear, both delivered as events.
- **Changing `wirelessAudioDelay` (Sonos audio delay) restarts the Sonos session.** URLs
  clear and the session drops and reconnects within about 5 seconds.
- **`player:volume` tracks the Sonos group volume during a Sonos session.** Verified
  live: writing 21 → 22 → 21 round-tripped with read-back and matching events. With no
  session it reads 0.
- **Role roots can't be listed.** `getRows` on `victrola:`, `player:`, `adchls:` returns
  `invalidPath`; `settings:/` can be walked. Live node names came from the firmware's
  `libnsdk_*.so` strings.
- **A missing node answers HTTP 500, not 200.** `getData` on an unknown path (e.g.
  `settings:/victrola/doesNotExist`) returns HTTP 500 with the `invalidPath` error body,
  not a 200 as older docs implied. `NsdkClient` checks every reply for an NSDK
  `{"error": {...}}` body regardless of status, mapping a name ending in `invalidPath` to
  `NsdkInvalidPath`; a non-200 reply with no error body becomes `NsdkConnectionError`.
- **Stream URLs read empty whenever no streaming session is active, not only in
  standby.** They exist only while a session runs, and arrive as events — read them
  fresh after every (re)connect, never cached. Standby is one way to have no session:
  after about 10 idle minutes (`settings:/system/maxIdleTime` = 600),
  `powermanager:target` reads `networkStandby` (reason `idleTimer`) and every
  `adchls:serverUrl*` node reads `""`, as in `tests/fixtures/get_data.json`. The API
  still answers. Treat an empty URL as "no stream right now", not an error. How the
  device wakes is still to be checked live.
- **An unknown or expired queue id answers HTTP 400 in plain text, not an NSDK error
  body.** Live probe 2026-10-03: `GET /api/event/pollQueue?queueId={00000000-0000-0000-
  0000-000000000000}&timeout=1` (a never-issued id) returned `400 Bad Request`,
  `Content-Type: text/plain`, body `Unknown queue id!` — no `{"error": {...}}` object at
  all. `NsdkClient` still only ever raises `NsdkConnectionError` for it: `resp.json()`
  fails to parse the non-JSON body (aiohttp's `ContentTypeError` for real, a
  `JSONDecodeError` against the fake), and both land in `_send`'s existing catch-all —
  no code change needed. `tests/fake_device.py`'s `_poll_queue` now returns this real
  shape (previously an UNVERIFIED placeholder `{"error": {"name": "queueNotFound",
  ...}}`), and `tests/test_nsdk_events.py`'s matching test now expects
  `NsdkConnectionError`, not `NsdkError` (it was asserting the placeholder's made-up
  shape, not the device's real one).
- **An event queue left unpolled expires on its own, within 14 minutes.** It then
  answers `pollQueue` the same way as a never-issued id: HTTP 400, `Unknown queue id!`.
  Don't assume a subscribed queue id stays valid indefinitely.
- **`network:wirelessRssi` pushed zero events over ~65 s when idle.** Live probe
  2026-10-03: subscribed to `network:wirelessRssi` alone and polled `timeout=5` for
  13 cycles (~65 s) with the device stationary on a stable Wi-Fi link; no event arrived.
  RSSI pushes are evidently change- or heartbeat-triggered, not continuous, so
  subscribing to it alongside the rest of `SUBSCRIBED_PATHS` is not a flood risk under
  normal conditions. A noisier radio environment or a longer sample could still see one;
  this one didn't.

## Live (e2e) testing

- **phacc's `pytest_runtest_setup` re-disables real sockets before every test;
  `socket_allow_hosts` alone cannot undo that.** `pytest_homeassistant_custom_component`
  0.13.367 (plugins.py ~line 195) runs for every test and calls
  `pytest_socket.socket_allow_hosts(["127.0.0.1"])` then
  `pytest_socket.disable_socket(allow_unix_socket=True)`. The second call replaces
  `socket.socket` with a guard class whose `__new__` raises `SocketBlockedError` for any
  non-Unix socket unconditionally, before a `connect()`-level allow-list is ever
  consulted. Measured directly: with only `socket_allow_hosts([VICTROLA_HOST,
  "127.0.0.1"])` in `tests/e2e/conftest.py`'s autouse fixture, every live request failed
  inside `aiohappyeyeballs` at the bare `socket.socket()` call with
  `HASocketBlockedError: A test tried to use socket.socket.`. Calling
  `pytest_socket.enable_socket()` first, then `socket_allow_hosts(...)`, fixed it.
- **aiohttp's `StreamReader.read(n)` returns as soon as any data is buffered, not once
  n bytes arrive.** Reading the live FLAC stream's first 64 KiB with
  `resp.content.read(65536)` returned after a single ~4 KiB TCP read — far too little
  for `ffprobe` to find a stream (it exits 1, "End of file"). `readexactly(65536)`
  (wrapped in `asyncio.timeout(5)`, catching both `TimeoutError` and
  `asyncio.IncompleteReadError`) accumulates across reads until it actually has the
  full 64 KiB or the deadline passes.

## Publishing

- **HACS validation can't read a private repo.** While the repo was private,
  `hacs/action` failed 2 of 9 checks: `hacsjson` ("invalid 'hacs.json' file") and
  `integration_manifest` ("expected a dictionary. Got None"). HACS downloads those two
  files from `raw.githubusercontent.com` with no token (`async_download_file` in
  hacs/integration), and a private repo answers 404. Not a repo defect: all 9 passed as
  soon as the repo went public, with only plan-doc commits in between (2026-10-03).

## Working with Doctor Biz

- **No port scans.** Don't port-scan devices on the LAN. Use protocol discovery (SSDP,
  mDNS, the device's own API) or ask Doctor Biz for a capture from `media-tools`, which
  sits on the device VLAN. This Mac can't reach that VLAN by multicast.
- **Ask before theorizing about state changes.** During live sessions Doctor Biz is
  changing the device too. When a value changes and we didn't cause it, ask "did you
  change X?" before building a theory on it. (The "UPnP mode falls back to Sonos" theory
  was just Doctor Biz flipping it back.)
- **Never write real private values into tracked files.** LAN IPs, Wi-Fi names,
  serials, MACs — not even inside a privacy-grep pattern meant to catch them. Keep them
  in the untracked `privacy-terms.local.md` and scan all history before publishing.
