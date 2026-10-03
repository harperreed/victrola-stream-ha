# Victrola Stream for Home Assistant — Implementation Plan

## Now
- Step: Tasks 1–13 complete and reviewed on `feat/v1` (89 offline tests + live e2e suite 4 pass/1 deferred; hassfest clean); final whole-branch review running (Opus)
- Next: one final fix wave (final-review findings + any live-checklist changes), then finishing-a-development-branch
- Open: Doctor Biz at the turntable for the Task 12 Step 3 live checklist (~15 min); Task 14 publish HELD until Doctor Biz says publish
- Approved: Design sections 1–3: "Looks right" (2026-10-03)
- Approved: Written spec: "let's build it. GO GO GO." (2026-10-03)
- Approved: Plan + execution method: "Subagent-driven (Recommended)" (2026-10-03)
- Compactions: 0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS-installable Home Assistant custom integration (`victrola_stream`) that controls and monitors a Victrola Stream turntable, reports when the platter spins and when it streams, and offers its live stream to any HA media player.

**Architecture:** A small async NSDK client (`nsdk.py`) speaks the turntable's port-80 HTTP API. A push-first `DataUpdateCoordinator` holds a single `VictrolaState` snapshot: one full read at start and every 5 minutes, and between those a long-poll on the device's event queue that applies each change as it arrives. Entities, the media source and diagnostics only ever read that snapshot. Writes go through the client as typed values and are confirmed by reading them back.

**Tech Stack:** Python ≥3.14.2, Home Assistant 2026.9.x, aiohttp (from HA), pytest + pytest-homeassistant-custom-component, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-10-03-victrola-stream-ha-design.md` (read it first; this plan argues from it). Device API reference: `../victrola-stream-go/docs/victrola-nsdk-api.md`, `../victrola-stream-go/docs/live-stream-discovery.md`, `gotchas.md`.

## Global Constraints

- Python `>=3.14.2`. Home Assistant 2026.9.x. `hacs.json` → `"homeassistant": "2026.9.0"`.
- `manifest.json`: domain `victrola_stream`, name `Victrola Stream`, version `0.1.0`, `integration_type: "device"`, `iot_class: "local_push"`, `config_flow: true`, `codeowners: ["@harperreed"]`, `requirements: []`. There are no third-party runtime dependencies; the HTTP session comes from `async_get_clientsession(hass)`.
- Every write to a value node sends a typed value `{"type": T, T: v}` and is confirmed by reading the node back. A mismatch raises. No optimistic state.
- Stream URLs are never cached across a reconnect. Read `adchls:serverUrl`, `adchls:serverUrl/mp3` and `adchls:serverUrl/flac` after every (re)connect and fresh when the media source resolves.
- Entities read only from the coordinator's `VictrolaState`; one source of truth.
- A node that answers `invalidPath` at setup gets no entity, and setup continues.
- Every hand-written source file (Python, shell) starts with two `# ABOUTME:` comment lines saying what the file does (after a shebang if there is one).
- Tests: no mocks of our own code. The HTTP boundary is faked only with recorded device payloads (`tests/fixtures/`). End-to-end tests use the real device and nothing else.
- Fixtures are sanitized real captures: device IP `192.0.2.10`, with no real serial, MAC, SSID, BSSID, Sonos RINCON id, Sonos household id or room names.
- Never port-scan. The e2e suite talks only to `$VICTROLA_HOST` port 80 and the stream URLs that host returns.
- Canonical check: `scripts/check` (ruff lint, ruff format check, pytest). It must pass before every commit. Conventional commits, one per task. Never bypass hooks.
- Work on branch `feat/v1`, cut from `main` before Task 1. Merging it back is Doctor Biz's call once Task 13 is done.

## Review Focus

1. **A device reboot while HA runs.** Polls fail, so the entities go unavailable; when the device answers again, the loop resubscribes and does a full read, and the stream URL sensors show the *new* ports. Pinned in Task 5 (`test_reconnect_rereads_urls`).
2. **A write the device "accepts" but ignores.** If the reply looks like success but the read-back value is unchanged, it must raise `NsdkWriteRejected` and never report success. Pinned in Task 3 (`test_set_typed_raises_when_readback_differs`).
3. **Speaker titles with HTML or odd characters.** A title like `<div style="…">DEFAULT SPEAKER</div>`, or names with `+` or `'`, must reach the select as clean text, and picking one must send the right `id`. Pinned in Task 2 (`test_row_title_strips_html`) and Task 9 (`test_default_speaker_select_sends_row_id`).
4. **Empty values and missing nodes.** `[{}]` (e.g. `hostlink:sonosConnected`) gives an entity state of unknown; `invalidPath` (a node another model lacks) gives no entity. Neither fails setup. Pinned in Task 5 (`test_full_read_records_missing_paths`) and Task 7 (`test_missing_node_creates_no_entity`).
5. **Output modes without Sonos speakers.** In UPnP, Roon or Bluetooth mode the speaker list has no Sonos rows, so the Default speaker select goes unavailable, and it comes back after switching to Sonos. The same applies to Volume in Sonos mode. Pinned in Task 9 (`test_default_speaker_unavailable_outside_sonos_mode`) and Task 8 (`test_volume_unavailable_in_sonos_mode`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `custom_components/victrola_stream/const.py` | Domain, node paths, poll/backoff constants, the subscribed-path list |
| `custom_components/victrola_stream/nsdk.py` | NSDK client: typed values, rows, reads, typed writes with read-back, activate, event queue, errors |
| `custom_components/victrola_stream/coordinator.py` | `VictrolaState` snapshot, `VictrolaCoordinator` (full read, push loop, writes) |
| `custom_components/victrola_stream/__init__.py` | Setup/unload, `VictrolaConfigEntry` alias, platform forwarding |
| `custom_components/victrola_stream/config_flow.py` | User, zeroconf and reconfigure steps |
| `custom_components/victrola_stream/entity.py` | `VictrolaEntity` base: device info, availability, snapshot access |
| `custom_components/victrola_stream/sensor.py`, `binary_sensor.py` | Read-only entities |
| `custom_components/victrola_stream/switch.py`, `number.py`, `button.py` | Simple write entities |
| `custom_components/victrola_stream/select.py` | Output, Default speaker and the enum settings |
| `custom_components/victrola_stream/media_source.py` | "Victrola Stream" in HA's media browser |
| `custom_components/victrola_stream/diagnostics.py` | Redacted snapshot download |
| `custom_components/victrola_stream/manifest.json`, `strings.json`, `translations/en.json`, `brand/` | Metadata, names, errors, icons |
| `scripts/check`, `scripts/e2e`, `scripts/capture_fixtures.py` | Canonical check, live suite, fixture recorder |
| `tests/fixtures/*.json` | Sanitized real device payloads |
| `tests/conftest.py`, `tests/test_*.py` | Unit and integration tests |
| `tests/e2e/test_live_onyx.py` | Real-device suite (skipped unless `VICTROLA_HOST` is set) |
| `pyproject.toml`, `hacs.json`, `README.md`, `LICENSE`, `CLAUDE.md`, `.gitignore` | Tooling and repo metadata |

---

### Task 1: Project skeleton, toolchain, and a discoverable integration

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `CLAUDE.md`, `hacs.json`, `scripts/check`
- Create: `custom_components/victrola_stream/__init__.py`, `custom_components/victrola_stream/const.py`, `custom_components/victrola_stream/manifest.json`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `DOMAIN = "victrola_stream"` in `const.py`.
  - An autouse fixture `auto_enable_custom_integrations(enable_custom_integrations)` in `tests/conftest.py`.
  - The canonical check `scripts/check`.
  - A `uv sync` environment with `pytest-homeassistant-custom-component==0.13.367`, the release that pins `homeassistant==2026.9.4` and needs Python ≥3.14.

- [ ] **Step 1: Create `pyproject.toml`.**
  - `[project]`: name `victrola-stream-ha`, version `0.1.0`, `requires-python = ">=3.14.2"`, `dependencies = []`.
  - `[dependency-groups] dev = ["pytest-homeassistant-custom-component==0.13.367", "ruff"]`.
  - `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`.
  - `[tool.ruff]`: `target-version = "py314"`, with lint `select = ["E", "F", "I", "UP", "B", "ASYNC", "RUF"]`.

  Run `uv sync`; expect a resolved environment on Python ≥3.14.2 (`uv python install 3.14` first if needed).

- [ ] **Step 2: Write the failing manifest test** in `tests/test_manifest.py`:

```python
async def test_manifest_is_discoverable(hass):
    m = (await async_get_integration(hass, DOMAIN)).manifest   # from homeassistant.loader
    assert (m["version"], m["iot_class"], m["integration_type"]) == ("0.1.0", "local_push", "device")
    assert m["config_flow"] is True and m["requirements"] == [] and m["codeowners"] == ["@harperreed"]
    assert m["zeroconf"] == [{"type": "_sues800device._tcp.local.", "properties": {"manufacturer": "victrola"}}]
```

- [ ] **Step 3: Run it to make sure it fails.** Run `uv run pytest tests/test_manifest.py -q`; expect FAIL (integration not found).

- [ ] **Step 4: Create the integration files.**
  - `manifest.json` per Global Constraints, plus `documentation` `https://github.com/harperreed/victrola-stream-ha` and `issue_tracker` `https://github.com/harperreed/victrola-stream-ha/issues`. The zeroconf matcher value is lowercase `victrola`, because HA lowercases the TXT value before its `fnmatch` (`zeroconf/discovery.py:90-96` at 2026.9.4).
  - `const.py` with `DOMAIN`.
  - `__init__.py` holding only its ABOUTME header for now.
  - `hacs.json`: `{"name": "Victrola Stream", "homeassistant": "2026.9.0"}`.

- [ ] **Step 5: Run it to make sure it passes.** Run `uv run pytest tests/test_manifest.py -q`; expect PASS.

- [ ] **Step 6: Create the repo plumbing.**
  - `scripts/check`: bash with an ABOUTME header and `set -euo pipefail`; runs `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest -q`, then prints `OK`. Make it executable.
  - `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.local.md`, `.dashboard/`.
  - `LICENSE`: MIT, "Copyright (c) 2026 Harper Reed".
  - `CLAUDE.md`. Names: the agent is **BIGFOOT BACKSPIN**, the human is **Doctor Biz**, a.k.a. **Vinyl Diesel**. Also: what this repo is; the commands (`uv sync`, `scripts/check`, `scripts/e2e`, `scripts/capture_fixtures.py`); the plan doc path and its Now section. Rules: read `gotchas.md` first; typed writes with read-back; never port-scan; fixtures sanitized; never cache stream URLs.

- [ ] **Step 7: Run the canonical check.** `scripts/check` should print `OK` with zero warnings in the pytest output. If pytest-asyncio warns about the fixture loop scope, set `asyncio_default_fixture_loop_scope = "function"`.

- [ ] **Step 8: Commit.**

```bash
git add pyproject.toml uv.lock .gitignore LICENSE CLAUDE.md hacs.json scripts/check custom_components tests
git commit -m "chore: project skeleton, toolchain and discoverable manifest"
```

---

### Task 2: Typed values, rows, errors, and real fixtures

**Files:**
- Create: `custom_components/victrola_stream/nsdk.py` (value, row and error types only in this task)
- Modify: `custom_components/victrola_stream/const.py` (all node paths and tuning constants; stdlib imports only, so the recorder can load it without HA)
- Create: `scripts/capture_fixtures.py`
- Create: `tests/fixtures/get_data.json`, `tests/fixtures/get_rows.json`, `tests/fixtures/events.json` (by running the recorder)
- Test: `tests/test_nsdk_values.py`, `tests/test_capture_fixtures.py`

**Interfaces:**
- Consumes: Task 1's project skeleton.
- Produces (in `nsdk.py`):
  - `@dataclass(frozen=True, slots=True) class NsdkValue: type: str; payload: Any`. `NsdkValue.from_json(obj: Any) -> NsdkValue` maps `{}`, `None` and a missing `type` to `EMPTY`; `{"type": T, T: v}` → `NsdkValue(T, v)`. It also has `is_empty: bool` (property), `as_bool() -> bool | None` (only `bool_`), `as_int() -> int | None` (`i16_`/`i32_`/`i64_`/`u32_`/`u64_`), `as_float() -> float | None` (`double_`/`flt_`), `as_str() -> str | None` (`string_`), `to_json() -> dict[str, Any]` (`{"type": T, T: payload}`), and classmethods `of_bool(v)`, `of_int(v)` (type `i32_`), `of_str(v)`. Module constant `EMPTY = NsdkValue("", None)`.
  - `@dataclass(frozen=True, slots=True) class NsdkRow: title: str; type: str | None; path: str | None; id: str | None; value: NsdkValue; preferred: bool`. `NsdkRow.from_json(obj: dict[str, Any]) -> NsdkRow` strips HTML tags from `title`, trims it, and maps `None` to `""`. `preferred` is `obj.get("preferred") is True`.
  - `class NsdkError(Exception)` with attributes `name: str`, `message: str`; subclasses `NsdkInvalidPath(NsdkError)` (when `name` ends with `invalidPath`) and `NsdkWriteRejected(NsdkError)`. `class NsdkConnectionError(Exception)` for transport failures, timeouts, and non-200 replies without an NSDK error body.
  - `const.py`, the single source of truth for node paths (stdlib only; it must not import `homeassistant`):
    - Tuning: `DOMAIN = "victrola_stream"`, `POLL_TIMEOUT_S = 25`, `BACKOFF_START_S = 1.0`, `BACKOFF_MAX_S = 30.0`, `FULL_REFRESH_INTERVAL = timedelta(minutes=5)`.
    - Identity: `NODE_SERIAL = "settings:/system/serialNumber"`, `NODE_MAC = "settings:/system/primaryMacAddress"`, `NODE_MANUFACTURER = "settings:/system/manufacturer"`, `NODE_PRODUCT = "settings:/system/productName"`, `NODE_DEVICE_NAME = "settings:/deviceName"`, `NODE_FIRMWARE = "settings:/version"`, `NODE_MCU_FIRMWARE = "hostlink:hostFirmwareVersion"`.
    - State: `NODE_MOTOR = "hostlink:motorDet"`, `NODE_SONOS_SESSION = "victrola:isConnectedToSonosGroup"`, `NODE_UPNP_STATE = "victrola:UpnpState"`, `NODE_VOLUME = "player:volume"`, `NODE_MUTE = "settings:/mediaPlayer/mute"`, `NODE_AUTOPLAY = "settings:/victrola/autoplay"`, `NODE_KNOB_BRIGHTNESS = "settings:/victrola/lightBrightness"`, `NODE_STREAMING_QUALITY = "settings:/victrola/forceLowBitrate"`, `NODE_SONOS_DELAY = "settings:/victrola/wirelessAudioDelay"`, `NODE_RCA_MODE = "settings:/adchls/dacMode"`, `NODE_RCA_DELAY = "settings:/adchls/dacDelay"`, `NODE_RCA_FIXED_VOLUME = "settings:/adchls/fixedVolume"`, `NODE_POWER = "powermanager:target"`, `NODE_NETWORK = "network:info"`, `NODE_RSSI_EVENT = "network:wirelessRssi"` (sends events only; it reads as empty).
    - Actions: `NODE_REBOOT = "powermanager:goReboot"`, `NODE_SET_DEFAULT_OUTPUT = "victrola:ui/setDefaultOutput"`.
    - `OUTPUT_TOGGLES: dict[str, str] = {"sonos": "settings:/victrola/sonosEnabled", "upnp": "settings:/victrola/upnpEnabled", "roon": "settings:/victrola/roonEnabled", "bluetooth": "settings:/victrola/bluetoothEnabled"}`; `SPEAKERS_PATH = "victrola:ui/speakerSelection"`; `URL_PATHS: dict[str, str] = {"hls": "adchls:serverUrl", "mp3": "adchls:serverUrl/mp3", "flac": "adchls:serverUrl/flac"}`.
    - `IDENTITY_PATHS`: the seven identity nodes. `STATE_PATHS`: the state nodes except `NODE_RSSI_EVENT`, plus the four output toggles and the three URL paths. `TRACKED_PATHS = IDENTITY_PATHS + STATE_PATHS + (NODE_RSSI_EVENT,)`. `SUBSCRIBED_PATHS`: `STATE_PATHS` minus `NODE_NETWORK`, plus `NODE_RSSI_EVENT`.
  - Fixture files: `get_data.json` = `{node_path: <exact getData?roles=value response JSON>}`; `get_rows.json` = `{node_path: <exact getRows response JSON>}`; `events.json` = a list of raw `pollQueue` response bodies.

- [ ] **Step 1: Write the failing value/row tests** in `tests/test_nsdk_values.py`:

```python
def test_value_parses_i32():
    assert NsdkValue.from_json({"type": "i32_", "i32_": 10}).as_int() == 10

def test_value_empty_object_and_null_are_empty():
    assert NsdkValue.from_json({}).is_empty and NsdkValue.from_json(None).is_empty

def test_value_custom_enum_type_keeps_payload():
    v = NsdkValue.from_json({"type": "forceLowBitrate", "forceLowBitrate": "losslessQuality"})
    assert (v.type, v.payload) == ("forceLowBitrate", "losslessQuality")

def test_value_wrong_accessor_returns_none():
    assert NsdkValue.from_json({"type": "string_", "string_": "x"}).as_int() is None

def test_value_to_json_is_typed_shape():
    assert NsdkValue.of_bool(True).to_json() == {"type": "bool_", "bool_": True}
    assert NsdkValue.of_int(17).to_json() == {"type": "i32_", "i32_": 17}

def test_row_title_strips_html():
    row = NsdkRow.from_json({"title": '<div style="margin: -32px 0px 0px 0px">DEFAULT SPEAKER</div>', "type": "header"})
    assert row.title == "DEFAULT SPEAKER" and row.value.is_empty and row.preferred is False
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_nsdk_values.py -q`; expect an ImportError for `NsdkValue`.

- [ ] **Step 3: Implement the value, row and error types in `nsdk.py`** with the signatures above. Port the parsing rules from `../victrola-stream-go/internal/nsdk/value.go` and the title cleaning from `clean()` in `../victrola-stream-go/internal/app/commands.go`.

- [ ] **Step 4: Run them to make sure they pass.** Run `uv run pytest tests/test_nsdk_values.py -q`; expect PASS.

- [ ] **Step 5: Write the failing recorder test** in `tests/test_capture_fixtures.py`. Load `scripts/capture_fixtures.py` with `importlib.util.spec_from_file_location`, then:

```python
def test_sanitize_replaces_discovered_private_values():
    raw = {"get_data": {"settings:/system/serialNumber": [{"type": "string_", "string_": "7a0a7a0a-1111-2222-3333-444455556666"}],
                        "network:info": [{"type": "networkInfo", "networkInfo": {"wireless": {"ssid": "home-wifi", "bssid": "AA:BB:CC:DD:EE:01", "mac": "AA:BB:CC:DD:EE:02", "addresses": [{"ip": "10.1.2.3", "protocol": "ipv4"}]}}}]},
           "get_rows": {"victrola:ui/speakerSelection": {"rows": [{"title": "Den + 2", "id": "RINCON_FAKEFAKEFAKE01400", "value": {"type": "sonosGroup", "sonosGroup": {"householdId": "Sonos_secretHOUSE", "leader": {"host": "10.1.2.9"}}}}]}},
           "events": []}
    out = json.dumps(capture.sanitize(raw, device_ip="10.1.2.3"))
    for secret in ("7a0a7a0a", "home-wifi", "AA:BB:CC:DD:EE", "10.1.2.", "RINCON_FAKE", "Sonos_secretHOUSE", "Den"):
        assert secret not in out
    assert "192.0.2.10" in out and "+ 2" in out
```

- [ ] **Step 6: Implement `scripts/capture_fixtures.py`** (stdlib only: `urllib`, `json`). The CLI is `uv run python scripts/capture_fixtures.py <host> <outdir>`.
  - It loads `custom_components/victrola_stream/const.py` by file path (`importlib.util.spec_from_file_location`), so the paths have one source. It reads `getData?roles=value` for every path in `IDENTITY_PATHS + STATE_PATHS`, plus `hostlink:sonosConnected` (an empty value) and `settings:/victrola/doesNotExist` (an `invalidPath` error body).
  - It reads `getRows` for `victrola:ui/speakerSelection` and records one `pollQueue` response: subscribe to `player:volume`, then poll with `timeout=2`.
  - `sanitize(raw: dict, device_ip: str) -> dict` discovers the private values in the capture (serial, `memberId`, MACs, SSID, BSSID, IPv4/IPv6 addresses, RINCON ids, the household id, room titles) and replaces each one everywhere in the text. The device IP becomes `192.0.2.10`, other IPv4 addresses `192.0.2.<n>`, IPv6 `2001:db8::<n>`, serials and UUIDs `00000000-0000-4000-8000-00000000000<n>`, MACs `02:00:00:00:00:<nn>`, the SSID `example-wifi`, RINCON ids `RINCON_<12 zero-padded digits>01400`, the household `Sonos_EXAMPLE`, and each room `Zone <n>` (keeping a `+ N` suffix).
  - It writes `get_data.json`, `get_rows.json` and `events.json`, then exits non-zero if any discovered private value survives anywhere in the output.

- [ ] **Step 7: Run the recorder against the live Onyx** (the record need not be playing): `uv run python scripts/capture_fixtures.py "$VICTROLA_HOST" tests/fixtures`. Expect three files written and exit 0. Open `get_rows.json` and confirm exactly one row has `"preferred": true` and that every title is a `Zone <n>` name.

- [ ] **Step 8: Add a privacy guard test** to `tests/test_capture_fixtures.py`: `test_fixtures_hold_no_private_values` reads all three fixture files and asserts that none contain `192.168.` or `Sonos_` other than `Sonos_EXAMPLE`, that every RINCON id matches `RINCON_\d{12}01400`, and that every MAC matches `02:00:00:00:00:[0-9A-F]{2}`. Run `uv run pytest tests/test_capture_fixtures.py -q`; expect PASS.

- [ ] **Step 9: Run the canonical check and commit.** `scripts/check` should end `OK`. Then:

```bash
git add custom_components/victrola_stream/nsdk.py custom_components/victrola_stream/const.py scripts/capture_fixtures.py tests/fixtures tests/test_nsdk_values.py tests/test_capture_fixtures.py
git commit -m "feat: NSDK typed values, rows and sanitized device fixtures"
```

---

### Task 3: NsdkClient reads, typed writes with read-back, activate, rows

**Files:**
- Modify: `custom_components/victrola_stream/nsdk.py`
- Create: `tests/fake_device.py`
- Test: `tests/test_nsdk_client.py`

**Interfaces:**
- Consumes: Task 2's types and fixtures; the `aioclient_mock` fixture (`AiohttpClientMocker` from `pytest_homeassistant_custom_component.test_util.aiohttp`). Its `side_effect` is an async callable `(method, url, data)` that returns an `AiohttpClientMockResponse`. Query matching is subset-based, and the first registered mock wins.
- Produces:
  - `class NsdkClient` with `__init__(self, session: aiohttp.ClientSession, host: str) -> None`, the read-only property `host: str`, and:
    - `async get_value(path: str) -> NsdkValue`
    - `async read_nodes(paths: Iterable[str]) -> tuple[dict[str, NsdkValue], frozenset[str]]`: concurrent reads. It returns the values plus the set of paths that answered `invalidPath`, and raises `NsdkConnectionError` if any read fails in transport.
    - `async get_rows(path: str, start: int = 0, end: int = 100) -> list[NsdkRow]`
    - `async set_typed(path: str, value: NsdkValue) -> NsdkValue`: POSTs `{"path": path, "role": "value", "value": value.to_json()}`, accepts a literal `true` or a `{"value": …}` object, then reads the node back and returns the read-back. It raises `NsdkWriteRejected` on a literal `false` or when the read-back differs from `value`.
    - `async activate(path: str, value: Any) -> None`: POSTs role `activate`, with the same reply rules and no read-back.
  - `tests/fake_device.py`: `class FakeVictrola`, a stateful stand-in for the device's HTTP API built only from recorded fixtures and verified behaviour. `FakeVictrola(aioclient_mock, host: str = "192.0.2.10")` registers side effects for `/api/getData`, `/api/getRows` and `/api/setData` (Task 4 adds the queue endpoints). Its public attributes are `values: dict[str, Any]` (path → getData body), `rows: dict[str, Any]`, `offline: bool` (every request raises `aiohttp.ClientConnectionError`), `ignore_writes: set[str]`, `reject_writes: set[str]` and `set_calls: list[dict[str, Any]]`.
  - The fake's `setData` behaves like the device:
    - role `value`: a path in `reject_writes` gets `false`. A path in `ignore_writes` gets `{"value": <current>, "timestamp": 1}` with nothing stored (the verified trap). Any other path stores `[value]` as its new getData body and gets `true` for `player:` paths or `{"value": value, "timestamp": 1}` otherwise.
    - role `activate`: recorded in `set_calls`, answered `true`.
  - An unknown getData path answers the recorded `invalidPath` body from `get_data.json["settings:/victrola/doesNotExist"]`, with its path text swapped.

- [ ] **Step 1: Write the failing client tests** in `tests/test_nsdk_client.py`. Each builds `client = NsdkClient(aioclient_mock.create_session(hass.loop), "192.0.2.10")` against a `FakeVictrola`.

```python
async def test_get_value_parses_typed_value(...):            # autoplay → as_bool() is True (per fixture)
async def test_get_value_keeps_path_characters_unescaped(...):
    await client.get_value("settings:/victrola/lightBrightness")
    assert "path=settings:/victrola/lightBrightness" in str(aioclient_mock.mock_calls[-1][1])
async def test_get_value_invalid_path_raises(...):            # pytest.raises(NsdkInvalidPath)
async def test_read_nodes_splits_missing_paths(...):          # missing == {"settings:/victrola/nope"}
async def test_offline_raises_connection_error(...):          # fake.offline = True → NsdkConnectionError
async def test_set_typed_sends_typed_body_and_reads_back(...):
    got = await client.set_typed("settings:/victrola/lightBrightness", NsdkValue.of_int(17))
    assert fake.set_calls[-1] == {"path": "settings:/victrola/lightBrightness", "role": "value", "value": {"type": "i32_", "i32_": 17}}
    assert got == NsdkValue.of_int(17)
async def test_set_typed_raises_when_readback_differs(...):   # ignore_writes → NsdkWriteRejected   (Review Focus 2)
async def test_set_typed_raises_on_false_reply(...):          # reject_writes → NsdkWriteRejected
async def test_activate_posts_activate_role(...):             # body role == "activate", value passed through
async def test_get_rows_parses_speakers(...):                 # rows with id; exactly one preferred; titles clean
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_nsdk_client.py -q`; expect FAIL (no `NsdkClient`).

- [ ] **Step 3: Implement `NsdkClient` and `FakeVictrola`.**
  - Requests: `GET http://{host}/api/getData` with `params={"path": p, "roles": "value"}`; `GET http://{host}/api/getRows` with `params={"path", "roles": "@all", "from", "to", "type": "structure"}`; `POST http://{host}/api/setData` with a `json=` body.
  - Timeouts: `aiohttp.ClientTimeout(total=10)`.
  - Error rules: map `aiohttp.ClientError` and `TimeoutError` to `NsdkConnectionError`; an `{"error": {"name", "message"}}` body (any status) to `NsdkError`, or to `NsdkInvalidPath` when the name ends in `invalidPath`.

- [ ] **Step 4: Run them to make sure they pass.** Run `uv run pytest tests/test_nsdk_client.py -q`; expect PASS.

- [ ] **Step 5: Run the canonical check and commit.** `scripts/check` should pass. Then:

```bash
git add custom_components/victrola_stream/nsdk.py tests/fake_device.py tests/test_nsdk_client.py
git commit -m "feat: NSDK client with typed writes confirmed by read-back"
```

---

### Task 4: Event queue in the client

**Files:**
- Modify: `custom_components/victrola_stream/nsdk.py`, `tests/fake_device.py`
- Test: `tests/test_nsdk_events.py`

**Interfaces:**
- Consumes: Task 3's `NsdkClient` and `FakeVictrola`.
- Produces:
  - `@dataclass(frozen=True, slots=True) class NsdkEvent: path: str; item_type: str; value: NsdkValue | None` with `NsdkEvent.from_json(obj) -> NsdkEvent`. `value` is `None` when there's no `itemValue`.
  - `NsdkClient.subscribe(paths: Iterable[str]) -> str`: POSTs `/api/event/modifyQueue` with `{"queueId": "", "subscribe": [{"path": p, "type": "itemWithValue"}…], "unsubscribe": []}`. It returns the server's queue id, which is the JSON string body (e.g. `"{2f…}"`), kept exactly, braces included.
  - `NsdkClient.poll(queue_id: str, timeout_s: int) -> list[NsdkEvent]`: `GET /api/event/pollQueue` with `params={"queueId": queue_id, "timeout": timeout_s}`. **The timeout is in seconds.** The HTTP timeout is `timeout_s + 10`. A `[]` body means no events.
  - `NsdkClient.unsubscribe(queue_id: str, paths: Iterable[str]) -> None`: the same endpoint, with `queueId` set and the paths moved to `unsubscribe`.
  - `FakeVictrola` additions:
    - `push_event(path: str, value_json: dict) -> None` sets `values[path] = [value_json]` and queues `{"itemType": "update", "path": path, "itemValue": value_json, "rowsEvents": []}` for every live queue.
    - `drop_queues() -> None` makes later polls on old ids return `{"error": {"name": "queueNotFound", "message": "unknown queue"}}`. This shape is **unverified**; it's labeled as such in the fake, and the client treats every error the same.
    - `poll_wait_s: float = 0.01` is how long a fake poll waits for an event before answering `[]`.
    - `subscribe_calls: list[dict]`.

- [ ] **Step 1: Write the failing event tests** in `tests/test_nsdk_events.py`:

```python
async def test_subscribe_returns_server_queue_id(...):     # body == {"queueId": "", "subscribe": [{"path": "player:volume", "type": "itemWithValue"}], "unsubscribe": []}; id starts "{" and ends "}"
async def test_poll_sends_seconds_timeout_and_queue_id(...):  # query has timeout=25 and the exact queue id
async def test_poll_parses_recorded_event(...):             # fixtures/events.json[0] → NsdkEvent(path="player:volume", item_type="update", value=NsdkValue("i32_", 0))
async def test_poll_returns_empty_list_on_timeout(...):
async def test_poll_error_body_raises_nsdk_error(...):      # after fake.drop_queues()
async def test_unsubscribe_sends_paths_in_unsubscribe(...):
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_nsdk_events.py -q`; expect FAIL.

- [ ] **Step 3: Implement `NsdkEvent`, `subscribe`, `poll` and `unsubscribe`, and the fake's queue endpoints.**

- [ ] **Step 4: Run them to make sure they pass.** Run `uv run pytest tests/test_nsdk_events.py -q`; expect PASS.

- [ ] **Step 5: Run the canonical check and commit.**

```bash
git add custom_components/victrola_stream/nsdk.py tests/fake_device.py tests/test_nsdk_events.py
git commit -m "feat: NSDK event queue subscribe/poll/unsubscribe"
```

---

### Task 5: Coordinator: snapshot, full read, push loop, confirmed writes

**Files:**
- Create: `custom_components/victrola_stream/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: every constant in `const.py` (Task 2); `NsdkClient`, `NsdkValue`, `NsdkRow`, `NsdkEvent` and the errors (Tasks 2–4); `FakeVictrola` (Tasks 3–4).
- Produces:
  - `coordinator.py`:
    - `@dataclass(frozen=True, slots=True) class Speaker: id: str; type: str; title: str; preferred: bool`. Built from `NsdkRow`s that have an `id`; rows without one, like headers and toggles, are skipped.
    - `@dataclass(frozen=True, slots=True) class VictrolaState: values: Mapping[str, NsdkValue]; missing: frozenset[str]; speakers: tuple[Speaker, ...]` with:
      - `value(path: str) -> NsdkValue` (`EMPTY` when absent)
      - the property `output -> str | None` (the key of the first `OUTPUT_TOGGLES` node reading `True`)
      - `stream_url(fmt: str) -> str | None` (`fmt` is a `URL_PATHS` key; returns `None` for an empty string)
      - `with_value(path: str, value: NsdkValue) -> VictrolaState` and `with_speakers(speakers) -> VictrolaState`, which return copies
    - `type VictrolaConfigEntry = ConfigEntry[VictrolaCoordinator]`.
    - `class VictrolaCoordinator(DataUpdateCoordinator[VictrolaState])`:
      - `__init__(hass, entry: VictrolaConfigEntry, client: NsdkClient)`, with `update_interval=FULL_REFRESH_INTERVAL` and `config_entry=entry`.
      - `client: NsdkClient`.
      - `async _async_update_data() -> VictrolaState`: `read_nodes(IDENTITY_PATHS + STATE_PATHS)` plus `get_rows(SPEAKERS_PATH)`. `NsdkConnectionError` or `NsdkError` becomes `UpdateFailed`.
      - `async_start_push() -> None`: starts the loop below with `entry.async_create_background_task`.
      - `async async_stop_push() -> None`: cancels the loop, then unsubscribes (best effort; errors are logged and swallowed).
      - `async async_write(path: str, value: NsdkValue) -> None`: `client.set_typed`, then `async_set_updated_data(self.data.with_value(path, readback))`. If `path` is an `OUTPUT_TOGGLES` node it also re-reads the speakers. `NsdkError` propagates to the caller.
      - `async async_activate(path: str, value: Any, *, reread_speakers: bool = False) -> None`.

The push loop (the one algorithm here that the signatures don't fix):

```python
async def _push_loop(self) -> None:
    backoff = BACKOFF_START_S
    resync = False
    while True:
        try:
            queue = await self.client.subscribe(SUBSCRIBED_PATHS)
            self._queue_id = queue
            if resync:                         # device came back: re-read everything, incl. new stream URLs
                await self.async_refresh()
                resync = False
            backoff = BACKOFF_START_S
            while True:
                events = await self.client.poll(queue, POLL_TIMEOUT_S)
                if events:
                    await self._apply(events)  # fold into a copy of self.data; re-read speakers if an output toggle changed;
                                               # NODE_RSSI_EVENT updates the rssi slot used by the Wi-Fi sensor
        except asyncio.CancelledError:
            raise
        except (NsdkError, NsdkConnectionError) as err:
            self._queue_id = None
            self.async_set_update_error(err)   # entities go unavailable now, not at the next 5-minute refresh
            resync = True
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
```

Subscribe before the resync read, so no change can slip between the read and the subscription. Events for paths outside `TRACKED_PATHS` are ignored; `NODE_RSSI_EVENT` is tracked, and the Wi-Fi sensor prefers it once an event has arrived. An event whose `value` is `None` is ignored too, except for output toggles, which trigger a speaker re-read.

- [ ] **Step 1: Write the failing coordinator tests** in `tests/test_coordinator.py`. Each test monkeypatches `coordinator.BACKOFF_START_S` to `0.01` and `coordinator.POLL_TIMEOUT_S` to `1`, and sets `fake.poll_wait_s = 0.01`. The coordinator gets a `MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10"}, unique_id=<fixture serial>)` and a client on `aioclient_mock.create_session(hass.loop)`.

```python
async def test_full_read_builds_snapshot(...):          # output == "sonos"; one preferred speaker; stream_url("flac") endswith "/stream.flac"
async def test_full_read_records_missing_paths(...):    # del fake.values[NODE_RCA_DELAY] → that path in data.missing; no exception   (Review Focus 4)
async def test_empty_value_reads_as_empty(...):         # fake.values[NODE_MOTOR] = [{}] → data.value(NODE_MOTOR).is_empty
async def test_full_read_failure_raises_update_failed(...)
async def test_push_applies_event(...):                 # push_event(NODE_MOTOR, {"type": "bool_", "bool_": False}) → data.value(NODE_MOTOR).as_bool() is False
async def test_output_toggle_event_rereads_speakers(...):  # swap fake.rows[SPEAKERS_PATH] to a no-Sonos-rows body, push sonosEnabled False → data.speakers == ()
async def test_reconnect_rereads_urls(...):             # (Review Focus 1)
    fake.offline = True
    # wait until coordinator.last_update_success is False
    fake.values[URL_PATHS["flac"]] = [{"type": "string_", "string_": "http://192.0.2.10:40000/stream.flac"}]
    fake.drop_queues(); fake.offline = False
    # wait until coordinator.data.stream_url("flac") == "http://192.0.2.10:40000/stream.flac" and last_update_success
async def test_async_write_updates_snapshot_from_readback(...)
async def test_async_write_propagates_rejection(...):   # ignore_writes → NsdkWriteRejected raised; snapshot unchanged
async def test_stop_push_unsubscribes(...):             # the last modifyQueue body has the paths under "unsubscribe"
```

Waiting helper: add `async def wait_for(predicate, timeout=2.0)` to `tests/conftest.py`. It polls `predicate()` every 0.01 s with `asyncio.sleep` and fails the test on timeout.

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_coordinator.py -q`; expect FAIL.

- [ ] **Step 3: Implement `const.py` and `coordinator.py`** to the interfaces and the loop above.

- [ ] **Step 4: Run them to make sure they pass.** Run `uv run pytest tests/test_coordinator.py -q`; expect PASS, with no "Task was destroyed but it is pending" warnings (the tests stop the push loop in teardown).

- [ ] **Step 5: Run the canonical check and commit.**

```bash
git add custom_components/victrola_stream/const.py custom_components/victrola_stream/coordinator.py tests/test_coordinator.py tests/conftest.py
git commit -m "feat: push-first coordinator with resync on reconnect"
```

---

### Task 6: Setup, unload, and the config flow

**Files:**
- Modify: `custom_components/victrola_stream/__init__.py`, `custom_components/victrola_stream/coordinator.py` (`async_shutdown` override)
- Create: `custom_components/victrola_stream/config_flow.py`, `custom_components/victrola_stream/strings.json`, `custom_components/victrola_stream/translations/en.json`
- Test: `tests/test_config_flow.py`, `tests/test_init.py`

**Interfaces:**
- Consumes:
  - `NsdkClient`, `VictrolaCoordinator`, `VictrolaConfigEntry`, the `NODE_*` constants and `FakeVictrola`.
  - HA 2026.9.4 APIs:
    - `from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, SOURCE_USER, SOURCE_ZEROCONF, SOURCE_RECONFIGURE`
    - `from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo`, with fields `ip_address, ip_addresses, port, hostname, type, name, properties`
    - `import voluptuous as vol` (HA installs probatio under that name)
    - `from homeassistant.helpers.aiohttp_client import async_get_clientsession`
    - `from homeassistant.const import CONF_HOST, Platform`
  - HA flow helpers: `_abort_if_unique_id_configured(updates=..., reload_on_update=True)`, `_abort_if_unique_id_mismatch(reason=...)`, `_get_reconfigure_entry()` and `async_update_reload_and_abort(entry, data_updates=...)`.
- Produces:
  - `__init__.py`:
    - `PLATFORMS: list[Platform] = []`. Tasks 7–9 append their platforms.
    - `async_setup_entry(hass, entry: VictrolaConfigEntry) -> bool`: build the client and coordinator, `await coordinator.async_config_entry_first_refresh()` (it raises `ConfigEntryNotReady` by itself), set `entry.runtime_data = coordinator`, call `coordinator.async_start_push()`, then forward the platforms.
    - `async_unload_entry(hass, entry) -> bool`: unload the platforms, then `await entry.runtime_data.async_shutdown()`.
  - `VictrolaCoordinator.async_shutdown()` overrides the base method: stop the push loop and unsubscribe, then `await super().async_shutdown()`. It must be idempotent.
  - `config_flow.py` has `class VictrolaConfigFlow(ConfigFlow, domain=DOMAIN)` with `VERSION = 1`, and these steps:
    - `async_step_user(user_input)`: the schema is `{vol.Required(CONF_HOST): str}`. It reads `NODE_SERIAL`, `NODE_MANUFACTURER` and `NODE_DEVICE_NAME`. Form errors: `cannot_connect` (an `NsdkConnectionError` or `NsdkError`) and `not_victrola` (manufacturer ≠ `Victrola`). It sets the unique ID to the serial, calls `_abort_if_unique_id_configured(updates={CONF_HOST: host})`, and creates the entry with title = device name and `data = {CONF_HOST: host}`.
    - `async_step_zeroconf(discovery_info)`: requires `properties["manufacturer"].lower() == "victrola"` (abort `not_victrola`) and a `serial` property (abort `cannot_connect` if missing). The host is `str(discovery_info.ip_address)`. It sets the unique ID to the TXT serial, updates the host on an existing entry, sets `self.context["title_placeholders"] = {"name": properties.get("name", "Victrola")}`, then moves to `async_step_zeroconf_confirm`.
    - `async_step_zeroconf_confirm(user_input)`: an empty-schema confirm form with the `{name}` placeholder, which then creates the entry.
    - `async_step_reconfigure(user_input)`: a host form defaulting to the current host. It identifies the device and sets the unique ID to its serial; `_abort_if_unique_id_mismatch(reason="wrong_device")`; then `async_update_reload_and_abort(self._get_reconfigure_entry(), data_updates={CONF_HOST: host})`.
  - `strings.json` keys:
    - `config.step.{user,zeroconf_confirm,reconfigure}`
    - `config.error.{cannot_connect,not_victrola}`
    - `config.abort.{already_configured,not_victrola,cannot_connect,wrong_device,reconfigure_successful}`
  - `translations/en.json` mirrors `strings.json`.

- [ ] **Step 1: Write the failing flow and setup tests.**

```python
# tests/test_config_flow.py (all with FakeVictrola; ZEROCONF_PROPS = {"name": "Record Player", "serial": <fixture serial>, "uuid": "stream1832victrola-00000000-0000-4000-8000-000000000002", "manufacturer": "Victrola", "ip": "192.0.2.10"})
async def test_user_flow_creates_entry(...):              # title == fixture device name; data == {"host": "192.0.2.10"}; unique_id == fixture serial
async def test_user_flow_cannot_connect(...):             # fake.offline → errors == {"base": "cannot_connect"}
async def test_user_flow_not_victrola(...):               # manufacturer node → "KEF" → errors == {"base": "not_victrola"}
async def test_user_flow_already_configured(...)
async def test_zeroconf_flow_creates_entry(...):          # zeroconf → form zeroconf_confirm → create_entry
async def test_zeroconf_updates_host_of_existing_entry(...):  # entry host 192.0.2.99 → abort already_configured; entry.data["host"] == "192.0.2.10"
async def test_zeroconf_ignores_non_victrola(...):        # manufacturer "KEF" → abort not_victrola
async def test_reconfigure_changes_host(...)
async def test_reconfigure_wrong_device_aborts(...):      # different serial → abort wrong_device
# tests/test_init.py
async def test_setup_and_unload(...):                     # state LOADED → unload → NOT_LOADED; last modifyQueue body has "unsubscribe" filled
async def test_setup_retries_when_offline(...):           # fake.offline → entry.state is ConfigEntryState.SETUP_RETRY
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_config_flow.py tests/test_init.py -q`; expect FAIL.

- [ ] **Step 3: Implement `__init__.py`, `config_flow.py`, the strings and translations, and the `async_shutdown` override.**

- [ ] **Step 4: Run them to make sure they pass**, then run `scripts/check` (expect `OK`).

- [ ] **Step 5: Commit.**

```bash
git add custom_components/victrola_stream tests/test_config_flow.py tests/test_init.py
git commit -m "feat: config flow (user, zeroconf, reconfigure) and entry setup"
```

---

### Task 7: Base entity, device card, sensors and binary sensors

**Files:**
- Create: `custom_components/victrola_stream/entity.py`, `custom_components/victrola_stream/sensor.py`, `custom_components/victrola_stream/binary_sensor.py`
- Modify: `__init__.py` (`PLATFORMS += [Platform.BINARY_SENSOR, Platform.SENSOR]`), `const.py` (`UPNP_STREAMING_STATES`), `strings.json`, `translations/en.json`
- Test: `tests/test_sensor.py`, `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes:
  - `VictrolaCoordinator`, `VictrolaState` and the constants.
  - HA: `CoordinatorEntity` (from `homeassistant.helpers.update_coordinator`) and `DeviceInfo`, `CONNECTION_NETWORK_MAC` (from `homeassistant.helpers.device_registry`).
  - `EntityCategory` (from `homeassistant.const`).
  - `SensorEntity`, `SensorEntityDescription`, `SensorDeviceClass.SIGNAL_STRENGTH`/`.ENUM` and `SensorStateClass.MEASUREMENT`; `SIGNAL_STRENGTH_DECIBELS_MILLIWATT`.
  - `BinarySensorEntity`, `BinarySensorEntityDescription`, `BinarySensorDeviceClass.RUNNING`.
- Produces:
  - `entity.py`:
    - `device_info(state: VictrolaState, host: str) -> DeviceInfo`:
      - identifiers `{(DOMAIN, serial)}`; connections `{(CONNECTION_NETWORK_MAC, primaryMacAddress.lower())}`
      - `manufacturer` (node), `model` = product name, `name` = device name
      - `sw_version` = `settings:/version`, `hw_version` = `hostlink:hostFirmwareVersion`, `serial_number` = serial
      - `configuration_url = f"http://{host}/webclient/"`
    - `class VictrolaEntity(CoordinatorEntity[VictrolaCoordinator])`: `_attr_has_entity_name = True`. `__init__(self, coordinator, description)` sets `entity_description`, `_attr_unique_id = f"{serial}_{description.key}"`, and `_attr_device_info`. `available` = `super().available and self.entity_description.available_fn(self.coordinator.data)`.
    - `@dataclass(frozen=True, kw_only=True) class VictrolaEntityDescriptionMixin`, with fields:
      - `node: str | None = None`: the node the entity reads or writes, if it has a single one.
      - `exists_fn: Callable[[VictrolaState], bool] | None = None`: is the entity created at setup? `None` means "`node` is `None`, or `node` isn't in `state.missing`".
      - `available_fn: Callable[[VictrolaState], bool]`: default always True.
  - `sensor.py`, with `value_fn: Callable[[VictrolaState], StateType]` on each description. Keys and translation keys:
    - `wifi_signal`: dBm, `SIGNAL_STRENGTH`, `MEASUREMENT`, diagnostic. The value is the latest `network:wirelessRssi` event when present, else `network:info` → `wireless.signalLevel`.
    - `power_state`: `ENUM` with options `["online", "network_standby"]`, mapped from the device's `online` and `networkStandby`. Any other device value gives `None` and one warning log. Diagnostic.
    - `stream_url_hls`, `stream_url_mp3`, `stream_url_flac`: diagnostic, value `state.stream_url(fmt)`.
  - `binary_sensor.py`:
    - `platter_spinning`: `RUNNING`, from `hostlink:motorDet` via `as_bool()`; `None` when the value is empty.
    - `streaming`: in Sonos mode, `isConnectedToSonosGroup.as_bool()`. In UPnP mode, `pstUpnpState in UPNP_STREAMING_STATES`, with `UPNP_STREAMING_STATES = frozenset({"playing"})` in `const.py` (marked "❓ verify in Task 12" in a comment). In any other mode, `available_fn` is False.
  - Platform setup: `async_setup_entry(hass, entry, async_add_entities)` adds one entity per description whose `exists_fn(coordinator.data)` is True.

- [ ] **Step 1: Write the failing tests:**

```python
async def test_sensors_report_fixture_values(...):        # wifi_signal == fixture signalLevel; power_state == "online"; stream_url_flac endswith "/stream.flac"
async def test_missing_node_creates_no_entity(...):       # del fake.values["network:info"] before setup → no wifi_signal in the entity registry   (Review Focus 4)
async def test_platter_follows_events(...):                # push motorDet False → state "off"; push True → "on"
async def test_streaming_on_in_sonos_mode(...)
async def test_streaming_unavailable_in_roon_mode(...):    # fixture toggles: sonos False, roon True → state "unavailable"
async def test_device_card(...):                           # device registry: manufacturer "Victrola", model "Victrola Stream", serial_number, hw_version, sw_version, mac connection
async def test_entities_unavailable_when_offline(...):     # fake.offline → states "unavailable" without waiting 5 minutes
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_sensor.py tests/test_binary_sensor.py -q`; expect FAIL.

- [ ] **Step 3: Implement `entity.py`, `sensor.py`, `binary_sensor.py`** and their entity names in `strings.json` and `translations/en.json`. Translation keys equal the description keys, including the `power_state` option names.

- [ ] **Step 4: Run them to make sure they pass**, then run `scripts/check` (expect `OK`).

- [ ] **Step 5: Commit.**

```bash
git add custom_components/victrola_stream tests/test_sensor.py tests/test_binary_sensor.py
git commit -m "feat: device card, Wi-Fi/power/stream-URL sensors, platter and streaming binary sensors"
```

---

### Task 8: Switches, numbers and the restart button

**Files:**
- Create: `custom_components/victrola_stream/switch.py`, `custom_components/victrola_stream/number.py`, `custom_components/victrola_stream/button.py`
- Modify: `entity.py` (write helper), `__init__.py` (`PLATFORMS += [Platform.BUTTON, Platform.NUMBER, Platform.SWITCH]`), `strings.json`, `translations/en.json`
- Test: `tests/test_switch.py`, `tests/test_number.py`, `tests/test_button.py`

**Interfaces:**
- Consumes:
  - `VictrolaEntity`, `VictrolaEntityDescriptionMixin`, `coordinator.async_write` and `coordinator.async_activate`.
  - HA: `SwitchEntity`/`SwitchEntityDescription`, `NumberEntity`/`NumberEntityDescription`/`NumberMode.SLIDER`, `ButtonEntity`/`ButtonEntityDescription`/`ButtonDeviceClass.RESTART`, `UnitOfTime.MILLISECONDS`.
  - `HomeAssistantError(translation_domain=, translation_key=, translation_placeholders=)` from `homeassistant.exceptions`.
- Produces:
  - `VictrolaEntity._async_write(path: str, value: NsdkValue) -> None` and `VictrolaEntity._async_activate(path: str, value: Any, *, reread_speakers: bool = False) -> None` map client errors to `HomeAssistantError(translation_domain=DOMAIN, …)`:
    - `NsdkWriteRejected` → `write_rejected`
    - `NsdkConnectionError` → `device_unreachable`
    - any other `NsdkError` → `device_error` (placeholder `{error}`)

    Add these keys under `"exceptions"` in `strings.json`.
  - Switches, where on and off write `NsdkValue.of_bool(True/False)`:
    - `mute`: `settings:/mediaPlayer/mute`
    - `autoplay`: `settings:/victrola/autoplay` (config)
    - `rca_fixed_volume`: `settings:/adchls/fixedVolume` (config)
  - Numbers, all writing `NsdkValue.of_int(int(value))`:
    - `volume`: `player:volume`, 0–100, step 1, `SLIDER`. `available_fn` = output in `{"upnp", "bluetooth"}`. Sonos-mode volume is phase 2, pending `victrola:getSonosVolume`/`setSonosVolume`.
    - `knob_brightness`: `settings:/victrola/lightBrightness`, 0–100, step 1, `SLIDER`, config.
    - `rca_delay`: `settings:/adchls/dacDelay`, 0–500, step 1, ms, config.
  - Button: `restart`, `RESTART`, config. Press → `_async_activate("powermanager:goReboot", True)`.

- [ ] **Step 1: Write the failing tests:**

```python
async def test_switch_turn_on_sends_typed_bool(...):       # fake.set_calls[-1] == {"path": "settings:/victrola/autoplay", "role": "value", "value": {"type": "bool_", "bool_": True}}; state "on"
async def test_switch_write_rejected_raises_and_keeps_state(...):  # ignore_writes → HomeAssistantError with translation_key "write_rejected"; state unchanged   (Review Focus 2)
async def test_number_sends_typed_int(...):                # knob_brightness → 17: value {"type": "i32_", "i32_": 17}; state "17"
async def test_volume_unavailable_in_sonos_mode(...):      # fixture is Sonos mode → "unavailable"; push upnpEnabled True + sonosEnabled False → available   (Review Focus 5)
async def test_restart_button_activates_reboot(...):       # set_calls[-1] == {"path": "powermanager:goReboot", "role": "activate", "value": True}
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_switch.py tests/test_number.py tests/test_button.py -q`; expect FAIL.

- [ ] **Step 3: Implement the write helpers and the three platforms**, with their names and exception strings.

- [ ] **Step 4: Run them to make sure they pass**, then run `scripts/check` (expect `OK`).

- [ ] **Step 5: Commit.**

```bash
git add custom_components/victrola_stream tests/test_switch.py tests/test_number.py tests/test_button.py
git commit -m "feat: switches, numbers and restart button with confirmed writes"
```

---

### Task 9: Selects — output, default speaker, enum settings

**Files:**
- Create: `custom_components/victrola_stream/select.py`
- Modify: `__init__.py` (`PLATFORMS += [Platform.SELECT]`), `strings.json`, `translations/en.json`
- Test: `tests/test_select.py`

**Interfaces:**
- Consumes: `VictrolaEntity` and its write helpers, `OUTPUT_TOGGLES`, `SPEAKERS_PATH`, `Speaker`; HA `SelectEntity`/`SelectEntityDescription`.
- Produces:
  - **`output`** (Output). Options are `["sonos", "upnp", "roon", "bluetooth"]`, with translated names Sonos, UPnP, Roon, Bluetooth; current = `state.output`. Selecting writes `NsdkValue.of_bool(True)` to `OUTPUT_TOGGLES[option]`. The device clears the others, and the coordinator re-reads the speakers (Task 5).
  - **`default_speaker`** (Default speaker). Options = `[s.title for s in state.speakers]`; current = the `preferred` speaker's title. Selecting calls `_async_activate("victrola:ui/setDefaultOutput", {"type": s.type, "id": s.id}, reread_speakers=True)` for the speaker with that title (the first one if titles repeat). `available_fn` = `state.output == "sonos" and bool(state.speakers)`.
  - **Enum settings**, all in the config category. Each has an `options_map: dict[str, str]` from option key to device value, and writes `NsdkValue(<device type>, <device value>)`:
    - `streaming_quality`: `settings:/victrola/forceLowBitrate`, device type `forceLowBitrate`, `{"connection_quality": "connectionQuality", "sound_quality": "soundQuality", "lossless_quality": "losslessQuality"}`, translated "Prioritize connection", "Standard", "Prioritize audio quality".
    - `sonos_audio_delay`: `settings:/victrola/wirelessAudioDelay`, device type `adchlsLatency`, `{"min": "min", "med": "med", "high": "high", "max": "max"}`.
    - `rca_mode`: `settings:/adchls/dacMode`, device type `adchlsDACMode`, `{"switching": "switching", "simultaneous": "simultaneous"}`.

    A device value missing from the map reads as `current_option = None`.

- [ ] **Step 1: Write the failing tests:**

```python
async def test_output_reports_current_mode(...):           # "sonos"
async def test_output_select_writes_toggle(...):            # select "upnp" → value {"type": "bool_", "bool_": True} to settings:/victrola/upnpEnabled
async def test_default_speaker_options_and_current(...):    # options == the fixture's Zone titles; current == the preferred one
async def test_default_speaker_select_sends_row_id(...):    # (Review Focus 3) rename one fixture row "Harper's Den + 2"; select it →
    # set_calls[-1] == {"path": "victrola:ui/setDefaultOutput", "role": "activate", "value": {"type": "victrolaOutputSonos", "id": <that row's id>}}
async def test_default_speaker_unavailable_outside_sonos_mode(...):  # push sonosEnabled False + upnpEnabled True, rows → none → "unavailable"; back to Sonos → available   (Review Focus 5)
async def test_enum_select_writes_typed_device_value(...):  # streaming_quality "sound_quality" → value {"type": "forceLowBitrate", "forceLowBitrate": "soundQuality"}
async def test_enum_unknown_device_value_reads_unknown(...)
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_select.py -q`; expect FAIL.

- [ ] **Step 3: Implement `select.py`** and its names and state translations.

- [ ] **Step 4: Run them to make sure they pass**, then run `scripts/check` (expect `OK`).

- [ ] **Step 5: Commit.**

```bash
git add custom_components/victrola_stream tests/test_select.py
git commit -m "feat: output, default speaker and setting selects"
```

---

### Task 10: Media source

**Files:**
- Create: `custom_components/victrola_stream/media_source.py`
- Test: `tests/test_media_source.py`

**Interfaces:**
- Consumes:
  - `VictrolaConfigEntry` (with `runtime_data`) and `URL_PATHS`.
  - From HA: `MediaSource`, `MediaSourceItem`, `PlayMedia` and `BrowseMediaSource` (in `homeassistant.components.media_source`, defined in `models.py`), plus `Unresolvable` from `homeassistant.components.media_source.error`. Also `MediaClass` and `MediaType` from `homeassistant.components.media_player`.
  - For the tests: `homeassistant.components.media_source.async_browse_media(hass, media_content_id)`, `async_resolve_media(hass, media_content_id, target_media_player)` and `generate_media_source_id(domain, identifier)`. Both helpers need `await async_setup_component(hass, "media_source", {})` first. The manifest doesn't need a `dependencies` entry for this.
- Produces:
  - `async def async_get_media_source(hass: HomeAssistant) -> VictrolaMediaSource`.
  - `class VictrolaMediaSource(MediaSource)` with `name = "Victrola Stream"` and `__init__(self, hass)` → `super().__init__(DOMAIN)`. Identifiers:
    - `""` (root): one child per loaded entry, with `identifier=entry.entry_id`, `title` = device name, `media_class=MediaClass.DIRECTORY`, `can_expand=True` and `can_play=False`.
    - `"<entry_id>"`: three children, `f"{entry_id}/{fmt}"` for `fmt` in `("hls", "mp3", "flac")`, titled "Live (HLS)", "Live (MP3)" and "Live (FLAC, Ogg)", with `media_class=MediaClass.MUSIC`, `can_play=True` and `can_expand=False`.
  - `async_resolve_media(item)` reads `URL_PATHS[fmt]` **fresh** with `coordinator.client.get_value`, never from the snapshot. It returns `PlayMedia(url=…, mime_type=…)`, with the MIME type from `{"hls": "application/vnd.apple.mpegurl", "mp3": "audio/mpeg", "flac": "audio/ogg"}`. An unknown entry or format, an empty URL, `NsdkError` or `NsdkConnectionError` all raise `Unresolvable` with a plain message.

- [ ] **Step 1: Write the failing tests:**

```python
async def test_browse_root_lists_turntable(...):          # one child, title == fixture device name
async def test_browse_turntable_lists_three_formats(...):  # identifiers end with /hls, /mp3, /flac; all can_play
async def test_resolve_reads_url_fresh(...):               # change fake.values[URL_PATHS["flac"]] after setup → resolved url is the NEW one; mime_type "audio/ogg"
async def test_resolve_offline_raises_unresolvable(...):   # fake.offline → pytest.raises(Unresolvable)
```

- [ ] **Step 2: Run them to make sure they fail.** Run `uv run pytest tests/test_media_source.py -q`; expect FAIL.

- [ ] **Step 3: Implement `media_source.py`.**

- [ ] **Step 4: Run them to make sure they pass**, then run `scripts/check` (expect `OK`).

- [ ] **Step 5: Commit.**

```bash
git add custom_components/victrola_stream/media_source.py tests/test_media_source.py
git commit -m "feat: live turntable streams in the media browser"
```

---

### Task 11: Diagnostics

**Files:**
- Create: `custom_components/victrola_stream/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `VictrolaConfigEntry`, `VictrolaState`, and `from homeassistant.components.diagnostics import async_redact_data`.
- Produces: `async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]`, returning `{"entry": async_redact_data(entry.as_dict(), {"host", "unique_id", "title"}), "state": async_redact_data(<state dict>, TO_REDACT)}`.
  - `<state dict>` is `{"values": {path: value.to_json()}, "missing": sorted(state.missing), "speakers": [asdict(s) for s in state.speakers]}`.
  - `TO_REDACT` covers:
    - the node paths `settings:/system/serialNumber`, `settings:/system/primaryMacAddress` and `settings:/system/memberId`, plus the three URL paths
    - the nested keys `ssid`, `bssid`, `mac`, `addresses`, `ip`, `gateways`, `dns`, `id`, `title`, `householdId` and `leader`

- [ ] **Step 1: Write the failing test** `test_diagnostics_redacts_private_values`. It sets up the entry and calls the function. Assertions: no fixture serial, MAC, SSID, speaker id or Zone title appears in `json.dumps(result)`; `"**REDACTED**"` does appear; and the `settings:/victrola/lightBrightness` value is still present.

- [ ] **Step 2: Run it to make sure it fails, implement, then run it to make sure it passes.** Run `uv run pytest tests/test_diagnostics.py -q`, then `scripts/check` (expect `OK`).

- [ ] **Step 3: Commit.**

```bash
git add custom_components/victrola_stream/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: redacted diagnostics"
```

---

### Task 12: Live end-to-end suite and the live checklist

**Files:**
- Create: `tests/e2e/__init__.py`, `tests/e2e/conftest.py`, `tests/e2e/test_live_onyx.py`, `scripts/e2e`
- Modify: this plan's Now section and checklist (record results), `custom_components/victrola_stream/const.py` (`UPNP_STREAMING_STATES`, if the live check says otherwise)

**Interfaces:**
- Consumes: the whole integration; the real Onyx at `$VICTROLA_HOST`; `ffprobe` on PATH.
- Produces:
  - `scripts/e2e`: bash with an ABOUTME header. It requires `VICTROLA_HOST` and runs `uv run pytest tests/e2e -q`.
  - `tests/e2e/conftest.py`:
    - Skips the module unless `VICTROLA_HOST` is set.
    - An autouse fixture that calls `pytest_socket.socket_allow_hosts([os.environ["VICTROLA_HOST"], "127.0.0.1"])`. phacc's `pytest_runtest_setup` allows only 127.0.0.1, but its DNS guard lets IP literals through, so `VICTROLA_HOST` must be an IP. If phacc's after-test socket check still fails, fall back to `pytest_socket.enable_socket()` in this conftest only, and note it in `gotchas.md`.
    - These tests must not use `aioclient_mock`.

- [ ] **Step 1: Write the live tests** in `tests/e2e/test_live_onyx.py`:

```python
async def test_live_config_flow_and_entities(hass):        # user flow with $VICTROLA_HOST → entry; platter binary_sensor is "on"/"off"; wifi_signal < 0
async def test_live_brightness_roundtrip(hass):            # read knob brightness n; set n+1 (n-1 at 100); entity shows it after read-back;
                                                           # a push event arrives (coordinator.data changes without a full refresh); restore n
async def test_live_stream_urls_answer(hass):              # each URL: HTTP 200 with content type application/vnd.apple.mpegurl / audio/mpeg / audio/ogg;
                                                           # if the first 64 KiB arrive within 5 s, ffprobe decodes them (flac → codec flac, 24-bit); otherwise skip ("no record playing")
async def test_live_media_source_resolves_current_url(hass):  # resolved flac url == fresh adchls:serverUrl/flac read
@pytest.mark.skipif(not os.environ.get("VICTROLA_E2E_ENUM_WRITE"), reason="touches audio settings; run with the turntable idle")
async def test_live_enum_write_roundtrip(hass):            # sonos_audio_delay: current → another option → back; read-back confirms both
```

- [ ] **Step 2: Run the suite against the Onyx.** Run `VICTROLA_HOST=<turntable IP> scripts/e2e`; expect PASS (the stream test may skip if no record is playing). Then run `VICTROLA_E2E_ENUM_WRITE=1 VICTROLA_HOST=<turntable IP> scripts/e2e -k enum` with the turntable idle; expect PASS. If the enum write fails, apply the spec's policy: the three enum entities move from `select` to read-only `sensor`. Record the outcome in `gotchas.md`.

- [ ] **Step 3: Run the live checklist with Doctor Biz at the turntable.** Ask for each physical action in turn and record the observed result in a "Live checklist" list under the Now section:
  - lift the needle and stop the platter → `platter_spinning` goes off (motorDet `false`)
  - wait for the session to end → `streaming` goes off
  - switch Output to UPnP from HA and start a record on a UPnP renderer → note the `pstUpnpState` value while streaming, and set `UPNP_STREAMING_STATES` to match
  - switch Output back to Sonos from HA
  - change Default speaker from HA, then back
  - press Restart → the device reboots, the entities go unavailable and recover, and the URL sensors show new ports
  - toggle Mute and Autoplay from HA, then restore them

  Any check that fails gets a failing test and a fix before this task closes.

- [ ] **Step 4: Run `scripts/check`** (expect `OK`), then commit:

```bash
git add tests/e2e scripts/e2e custom_components/victrola_stream/const.py gotchas.md docs/superpowers/plans/2026-10-03-victrola-stream-ha.md
git commit -m "test: live end-to-end suite against the Onyx and checklist results"
```

---

### Task 13: README, brand images, local hassfest

**Files:**
- Create: `README.md`, `docs/brand/icon.svg`, `docs/brand/logo.svg`, `custom_components/victrola_stream/brand/icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`
- Modify: `CLAUDE.md` if any command changed

**Interfaces:**
- Consumes: the finished integration.
- Produces: user documentation; brand images in `custom_components/victrola_stream/brand/` (the file names HA 2026.3+ reads for custom integrations); a clean local hassfest run.

- [ ] **Step 1: Write `README.md`.** Cover:
  - what the integration does
  - supported models: Onyx verified; Carbon, Pearl and Sapphire expected but untested
  - installing it from HACS as a custom repository
  - setup: zeroconf where mDNS reaches, otherwise by IP; the reconfigure step for VLAN'd networks
  - an entity table
  - playing the turntable on other players through the media browser (FLAC is Ogg-wrapped)
  - two automation examples: platter spinning → lights, and streaming → media player
  - limitations: motor ≠ needle; Volume is unavailable in Sonos mode; no cloud
  - development: `uv sync`, `scripts/check`, `scripts/e2e` and the fixture recorder

  Use RFC 5737 addresses (`192.0.2.10`) in every example.

- [ ] **Step 2: Draw a simple flat turntable glyph** as `docs/brand/icon.svg` (square) and `docs/brand/logo.svg` (wide). Rasterize them with `rsvg-convert`: `icon.png` 256×256, `icon@2x.png` 512×512, `logo.png` with its short side 256, and `logo@2x.png` with its short side 512. These are the home-assistant/brands repo's conventions; HA's local-brand docs don't state pixel sizes. Check the sizes with `sips -g pixelWidth -g pixelHeight custom_components/victrola_stream/brand/*.png`.

- [ ] **Step 3: Run hassfest locally.** Run `docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest` from the repo root; this machine runs Docker on Colima, which shares `$HOME`. Expect no errors. Fix every finding at its root cause.

- [ ] **Step 4: Run `scripts/check`** (expect `OK`), then commit:

```bash
git add README.md docs/brand custom_components/victrola_stream/brand CLAUDE.md
git commit -m "docs: README and brand images; hassfest clean"
```

---

### Task 14: Publish to GitHub (HELD: needs Doctor Biz's explicit go-ahead)

Publishing is outward-facing. Don't start this task until Doctor Biz says to publish, and record the exact words in the Now section first.

**Files:**
- Create: `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: the finished, green repo from Tasks 1–13.
- Produces: the public repo `github.com/harperreed/victrola-stream-ha`, with CI running hassfest, HACS validation and pytest, and a `v0.1.0` release.

- [ ] **Step 1: Write `.github/workflows/validate.yml`.** Trigger on `push`, `pull_request` and `workflow_dispatch`. Three jobs:
  - `hassfest`: `actions/checkout@v4`, then `home-assistant/actions/hassfest@master`.
  - `hacs`: `hacs/action@main` with `category: integration`.
  - `tests`: `actions/checkout@v4`, `astral-sh/setup-uv` (the current major tag), then `uv sync` and `scripts/check`.

- [ ] **Step 2: Re-run the privacy guard on everything about to go public: the tree and every commit.** Run `uv run pytest tests/test_capture_fixtures.py -q` (PASS). The private search terms (the device's real addresses, network names and ids) never go in a tracked file, this plan included. They live one per line in `privacy-terms.local.md` in the repo root, which `.gitignore`'s `*.local.md` rule keeps out of git. If that file is missing or empty, stop and ask Doctor Biz for the terms: `git grep` given no patterns prints nothing, which reads as a pass. Then:
  - `git check-ignore -q privacy-terms.local.md && test -s privacy-terms.local.md` must succeed.
  - `git grep -nE -f privacy-terms.local.md $(git rev-list --all)` must print nothing. It searches every file of every commit, not just the tree.
  - `git log --all --format=%B | grep -nE -f privacy-terms.local.md` must print nothing; commit messages get published too.
  - A hit in history means rewriting history before Step 3 pushes it. That destroys commits, so it happens only on Doctor Biz's explicit go-ahead, recorded in the Now section; rerun this step afterwards.

- [ ] **Step 3: Ask Doctor Biz** whether the repo should be public or private, then create it with the remote: `gh repo create harperreed/victrola-stream-ha --<public|private> --source . --description "Home Assistant integration for Victrola Stream turntables (HACS)"`. Push `main`, and add the topics `home-assistant`, `hacs`, `victrola`, `turntable`.

- [ ] **Step 4: Watch CI.** Run `gh run watch` and expect all three jobs green. Fix any finding at its root cause, then commit and push again.

- [ ] **Step 5: Tag and release.** `git tag v0.1.0 && git push --tags`, then `gh release create v0.1.0 --title "v0.1.0" --notes-file <generated notes>`. Finally, check in the HACS UI that the repo installs as a custom repository (Doctor Biz's instance).
