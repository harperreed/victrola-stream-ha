#!/usr/bin/env python3
# ABOUTME: Records real getData/getRows/pollQueue responses from a live Victrola device.
# ABOUTME: Sanitizes every private value found before writing tests/fixtures/*.json.
from __future__ import annotations

import importlib.util
import ipaddress
import itertools
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
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
# way. MAC/RINCON/UUID/household/IPv4 each have a rigid, unambiguous shape, so
# a word-bounded regex finds them directly as a text substitution.
#
# IPv6 does not get the same treatment. `::` compression means a valid
# address can start, end, or hide its zero run anywhere in the middle, and it
# can even embed a dotted IPv4 tail (`::ffff:192.0.2.1`); no fixed-shape regex
# finds every one of those forms without mis-splitting at least one of them
# (this file's own history: one regex missed `fe80::1a2b` entirely or
# truncated `2001:db8::1` to `2001:db8`, depending on digit parity; loosening
# it to also find a leading `::` loosens it past a dot too, mis-splitting the
# embedded-IPv4 form at the first "."). Every address this device reports is
# its own complete JSON string value, never embedded in a larger string, so
# IPv6 is instead found by walking the parsed capture and testing whole
# string values with the stdlib `ipaddress` module — there is no substring to
# mis-bound, so that whole class of bug cannot recur. The leak check below
# re-derives IPv6 the same way, independently, from the finished output.

_MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
_RINCON_RE = re.compile(r"RINCON_[0-9A-Za-z]+")
_UUID_RE = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b"
)
_HOUSEHOLD_RE = re.compile(r"Sonos_[\w.]+")
_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_ROOM_SUFFIX_RE = re.compile(r"(\s+\+\s+\d+)$")


def _is_ipv6(value: str) -> bool:
    """True when value is a complete, valid IPv6 address, per ipaddress.

    A MAC's 6 colon-separated groups fail this (no `::` means 8 groups are
    required), so the same check both accepts every `::` shape and keeps
    MACs out, with no shape-guessing of its own.
    """
    if ":" not in value:
        return False
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


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


def _all_string_values(obj: Any) -> Iterator[str]:
    """Walk a parsed JSON value, yielding every string anywhere inside it."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _all_string_values(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_string_values(item)


def _speaker_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    speakers = raw.get("get_rows", {}).get(const.SPEAKERS_PATH, {})
    rows = speakers.get("rows", []) if isinstance(speakers, dict) else []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def _sanitize_text(text: str, original: str, replacement: str) -> str:
    """Replace one exact string value everywhere it appears as a JSON string."""
    return text.replace(json.dumps(original), json.dumps(replacement))


def _sanitize_ipv6(text: str, raw: dict[str, Any]) -> str:
    """Replace every IPv6 address found among raw's string values.

    Walks `raw` rather than scanning `text` with a regex — see the module
    note above. Runs first, against the still-untouched `text`, so no later
    pass's placeholder can be mistaken for an IPv6 candidate.
    """
    seen: dict[str, str] = {}
    counter = itertools.count(1)
    for value in dict.fromkeys(_all_string_values(raw)):
        if not _is_ipv6(value):
            continue
        if value not in seen:
            seen[value] = f"2001:db8::{next(counter)}"
        text = _sanitize_text(text, value, seen[value])
    return text


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
    text = _sanitize_ipv6(text, raw)
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
    return bad


def _ipv6_leaks(sanitized: dict[str, Any]) -> list[str]:
    """Independently re-check every string value for an unredacted IPv6 address.

    Re-derives the answer from scratch by walking `sanitized` itself, rather
    than trusting whatever `_sanitize_ipv6` claims to have already handled:
    a future regression in that pass (a skipped branch, a reintroduced
    regex, ...) still gets caught here, because this check never depends on
    its bookkeeping, only on the finished output.
    """
    return [
        value
        for value in _all_string_values(sanitized)
        if _is_ipv6(value) and not value.startswith("2001:db8:")
    ]


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
    return (
        _shape_violations(text) + _structural_leaks(raw, text) + _ipv6_leaks(sanitized)
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <host> <outdir>", file=sys.stderr)
        return 2
    host, outdir = argv[1], argv[2]
    out_dir = Path(outdir)

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

    # Validate before writing anything: a run that fails this check must leave
    # tests/fixtures/ untouched, not a possibly-leaking partial write sitting
    # in the tracked directory waiting for an operator to notice a bad exit
    # code before `git add`-ing it anyway.
    leaks = check_sanitized(raw, sanitized)
    if leaks:
        print(
            f"capture_fixtures: private values survived sanitizing: {leaks!r}",
            file=sys.stderr,
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("get_data", "get_rows", "events"):
        (out_dir / f"{name}.json").write_text(
            json.dumps(sanitized[name], indent=2, sort_keys=True) + "\n"
        )

    print(
        f"wrote {out_dir}/get_data.json, {out_dir}/get_rows.json, {out_dir}/events.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
