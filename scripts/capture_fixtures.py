#!/usr/bin/env python3
# ABOUTME: Records real getData/getRows/pollQueue responses from a live Victrola device.
# ABOUTME: Sanitizes every private value found before writing tests/fixtures/*.json.
from __future__ import annotations

import importlib.util
import itertools
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

_CONST_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "victrola_stream"
    / "const.py"
)


def _load_const() -> Any:
    """Load const.py by file path, the same single source of truth HA uses."""
    spec = importlib.util.spec_from_file_location("victrola_stream_const", _CONST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


const = _load_const()

# Real pollQueue bodies recorded from this device on 2026-10-02 (controller
# ruling R4): a live 2-second poll almost always returns [], so these two
# substitute a real volume-change event observed in a controller session and
# the motorDet event documented in
# ../victrola-stream-go/docs/live-stream-discovery.md. Neither carries any
# device-specific or private data.
_RECORDED_VOLUME_EVENT: list[dict[str, Any]] = [
    {
        "itemType": "update",
        "path": "player:volume",
        "itemValue": {"type": "i32_", "i32_": 0},
        "rowsEvents": [],
    }
]
_RECORDED_MOTOR_EVENT: list[dict[str, Any]] = [
    {
        "itemType": "update",
        "path": "hostlink:motorDet",
        "itemValue": {"type": "bool_", "bool_": True},
        "rowsEvents": [],
    }
]

_REQUEST_TIMEOUT_S = 10
_PATH_SAFE_CHARS = ":/@,._-"


def _query_escape(value: str) -> str:
    """Percent-encode a query value but leave NSDK path characters intact."""
    return urllib.parse.quote(value, safe=_PATH_SAFE_CHARS)


def _get_json(url: str | urllib.request.Request, timeout: float) -> Any:
    """Fetch and parse a JSON body, on a 2xx or an HTTP error status alike.

    An unknown path's invalidPath error body arrives over HTTP 500 on this
    firmware, not 200; the recorder's job is to capture it, not judge it.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return json.loads(error.read())


def _get_data(host: str, path: str) -> Any:
    url = f"http://{host}/api/getData?path={_query_escape(path)}&roles=value"
    return _get_json(url, timeout=_REQUEST_TIMEOUT_S)


def _get_rows(host: str, path: str) -> Any:
    url = (
        f"http://{host}/api/getRows?path={_query_escape(path)}"
        "&roles=@all&from=0&to=100&type=structure"
    )
    return _get_json(url, timeout=_REQUEST_TIMEOUT_S)


def _modify_queue(host: str, subscribe_paths: list[str]) -> str:
    payload = {
        "queueId": "",
        "subscribe": [{"path": p, "type": "itemWithValue"} for p in subscribe_paths],
        "unsubscribe": [],
    }
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://{host}/api/event/modifyQueue",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    return _get_json(request, timeout=_REQUEST_TIMEOUT_S)


def _poll_queue(host: str, queue_id: str, timeout_s: int) -> Any:
    encoded_id = urllib.parse.quote(queue_id, safe="")
    url = f"http://{host}/api/event/pollQueue?queueId={encoded_id}&timeout={timeout_s}"
    return _get_json(url, timeout=timeout_s + _REQUEST_TIMEOUT_S)


# --- Sanitizing -------------------------------------------------------------
#
# sanitize() works on the capture's JSON text rather than walking a fixed
# schema, so a private value nested under any node path is caught the same
# way. The passes below run in an order where no category's own placeholder
# can be mistaken for another category's input: IPv6 runs before MAC because
# a bare MAC is a degenerate case of the broad hex-group pattern IPv6
# addresses need; MAC, RINCON, UUID, household and IPv4 don't overlap each
# other or anything IPv6 leaves behind.

_MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
_HEX_GROUP_RE = re.compile(r"\b[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{0,4}){2,7}\b")
_RINCON_RE = re.compile(r"RINCON_[0-9A-Za-z]+")
_UUID_RE = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b"
)
_HOUSEHOLD_RE = re.compile(r"Sonos_[\w.]+")
_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_ROOM_SUFFIX_RE = re.compile(r"(\s+\+\s+\d+)$")


def _is_mac_shaped(token: str) -> bool:
    groups = token.split(":")
    return len(groups) == 6 and all(len(g) == 2 for g in groups)


def _counting_sub(
    pattern: re.Pattern[str],
    text: str,
    template: Callable[[int], str],
    normalize: Callable[[str], str] = str.upper,
) -> str:
    """Replace every match with template(n), numbering distinct matches in order."""
    seen: dict[str, str] = {}
    counter = itertools.count(1)

    def repl(match: re.Match[str]) -> str:
        key = normalize(match.group(0))
        if key not in seen:
            seen[key] = template(next(counter))
        return seen[key]

    return pattern.sub(repl, text)


def _sanitize_ipv6(text: str) -> str:
    seen: dict[str, str] = {}
    counter = itertools.count(1)

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        if "::" not in token and _is_mac_shaped(token):
            return token  # a MAC, not an IPv6 address; leave it for the MAC pass
        if token not in seen:
            seen[token] = f"2001:db8::{next(counter)}"
        return seen[token]

    return _HEX_GROUP_RE.sub(repl, text)


def _sanitize_ipv4(text: str, device_ip: str) -> str:
    seen: dict[str, str] = {device_ip: "192.0.2.10"}
    counter = itertools.count(1)

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        if token not in seen:
            n = next(counter)
            while n == 10:  # reserved for the device's own address
                n = next(counter)
            seen[token] = f"192.0.2.{n}"
        return seen[token]

    return _IPV4_RE.sub(repl, text)


def _find_by_key(obj: Any, key: str) -> list[str]:
    """Recursively collect string values stored under an exact dict key."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, str) and v:
                found.append(v)
            else:
                found.extend(_find_by_key(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_by_key(item, key))
    return found


def _speaker_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    speakers = raw.get("get_rows", {}).get(const.SPEAKERS_PATH, {})
    rows = speakers.get("rows", []) if isinstance(speakers, dict) else []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def _sanitize_text(text: str, original: str, replacement: str) -> str:
    """Replace one exact string value everywhere it appears as a JSON string."""
    return text.replace(json.dumps(original), json.dumps(replacement))


def _sanitize_ssids(text: str, raw: dict[str, Any]) -> str:
    for ssid in dict.fromkeys(_find_by_key(raw, "ssid")):
        text = _sanitize_text(text, ssid, "example-wifi")
    return text


def _sanitize_room_titles(text: str, raw: dict[str, Any]) -> str:
    counter = itertools.count(1)
    for row in _speaker_rows(raw):
        title = row.get("title") or ""
        if not title:
            continue
        suffix_match = _ROOM_SUFFIX_RE.search(title)
        suffix = suffix_match.group(1) if suffix_match else ""
        text = _sanitize_text(text, title, f"Zone {next(counter)}{suffix}")
    return text


def sanitize(raw: dict[str, Any], device_ip: str) -> dict[str, Any]:
    """Replace every private value this capture holds with a fixed placeholder.

    Device IP -> 192.0.2.10; other IPv4 -> 192.0.2.<n>; IPv6 -> 2001:db8::<n>;
    serials/UUIDs -> 00000000-0000-4000-8000-00000000000<n>; MACs/BSSIDs ->
    02:00:00:00:00:<nn>; RINCON ids -> RINCON_<12 digits>01400; the Sonos
    household -> Sonos_EXAMPLE; SSID -> example-wifi; room titles -> "Zone
    <n>", keeping any "+ N" grouped-speaker suffix.
    """
    text = json.dumps(raw)
    text = _sanitize_ipv6(text)
    text = _counting_sub(_MAC_RE, text, lambda n: f"02:00:00:00:00:{n:02d}")
    text = _counting_sub(_RINCON_RE, text, lambda n: f"RINCON_{n:012d}01400")
    text = _counting_sub(
        _UUID_RE,
        text,
        lambda n: f"00000000-0000-4000-8000-{n:012d}",
        normalize=str.lower,
    )
    text = _HOUSEHOLD_RE.sub("Sonos_EXAMPLE", text)
    text = _sanitize_ipv4(text, device_ip)
    text = _sanitize_ssids(text, raw)
    text = _sanitize_room_titles(text, raw)
    return json.loads(text)


def _shape_violations(text: str) -> list[str]:
    """Return every regex-discovered match whose shape is not the safe placeholder."""
    bad: list[str] = []
    for match in _MAC_RE.findall(text):
        if not re.fullmatch(r"02:00:00:00:00:[0-9A-Fa-f]{2}", match):
            bad.append(match)
    for match in _RINCON_RE.findall(text):
        if not re.fullmatch(r"RINCON_\d{12}01400", match):
            bad.append(match)
    for match in _UUID_RE.findall(text):
        if not re.fullmatch(r"00000000-0000-4000-8000-\d{12}", match):
            bad.append(match)
    for match in _HOUSEHOLD_RE.findall(text):
        if match != "Sonos_EXAMPLE":
            bad.append(match)
    for match in _IPV4_RE.findall(text):
        if not match.startswith("192.0.2."):
            bad.append(match)
    for match in _HEX_GROUP_RE.findall(text):
        if "::" not in match and _is_mac_shaped(match):
            continue  # a MAC; already checked above
        if not match.startswith("2001:db8:"):
            bad.append(match)
    return bad


def _structural_leaks(raw: dict[str, Any], text: str) -> list[str]:
    """Return original ssid/title/memberId values that still appear verbatim."""
    candidates = [
        *_find_by_key(raw, "ssid"),
        *_find_by_key(raw, "memberId"),
        *(row.get("title") or "" for row in _speaker_rows(raw)),
    ]
    return [value for value in candidates if value and json.dumps(value) in text]


def check_sanitized(raw: dict[str, Any], sanitized: dict[str, Any]) -> list[str]:
    """Return every private value that survived sanitizing, or [] when clean."""
    text = json.dumps(sanitized)
    return _shape_violations(text) + _structural_leaks(raw, text)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <host> <outdir>", file=sys.stderr)
        return 2
    host, outdir = argv[1], argv[2]
    out_dir = Path(outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = [
        *const.IDENTITY_PATHS,
        *const.STATE_PATHS,
        "hostlink:sonosConnected",
        "settings:/victrola/doesNotExist",
    ]
    get_data = {path: _get_data(host, path) for path in paths}
    get_rows = {const.SPEAKERS_PATH: _get_rows(host, const.SPEAKERS_PATH)}

    queue_id = _modify_queue(host, [const.NODE_VOLUME])
    live_poll = _poll_queue(host, queue_id, timeout_s=2)

    raw = {"get_data": get_data, "get_rows": get_rows, "events": [live_poll]}
    sanitized = sanitize(raw, device_ip=host)
    sanitized["events"] = [
        *sanitized["events"],
        _RECORDED_VOLUME_EVENT,
        _RECORDED_MOTOR_EVENT,
    ]

    for name in ("get_data", "get_rows", "events"):
        (out_dir / f"{name}.json").write_text(
            json.dumps(sanitized[name], indent=2, sort_keys=True) + "\n"
        )

    leaks = check_sanitized(raw, sanitized)
    if leaks:
        print(
            f"capture_fixtures: private values survived sanitizing: {leaks!r}",
            file=sys.stderr,
        )
        return 1

    print(
        f"wrote {out_dir}/get_data.json, {out_dir}/get_rows.json, {out_dir}/events.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
