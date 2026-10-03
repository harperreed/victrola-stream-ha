# ABOUTME: Tests for the fixture recorder: its sanitizing rules and committed output.
# ABOUTME: Loads scripts/capture_fixtures.py by path, as the recorder loads const.py.
import importlib.util
import json
import re
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "capture_fixtures.py"
)
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_capture_module():
    spec = importlib.util.spec_from_file_location("capture_fixtures", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = _load_capture_module()


def test_sanitize_replaces_discovered_private_values():
    raw = {
        "get_data": {
            "settings:/system/serialNumber": [
                {"type": "string_", "string_": "7a0a7a0a-1111-2222-3333-444455556666"}
            ],
            "network:info": [
                {
                    "type": "networkInfo",
                    "networkInfo": {
                        "wireless": {
                            "ssid": "home-wifi",
                            "bssid": "AA:BB:CC:DD:EE:01",
                            "mac": "AA:BB:CC:DD:EE:02",
                            "addresses": [{"ip": "10.1.2.3", "protocol": "ipv4"}],
                        }
                    },
                }
            ],
        },
        "get_rows": {
            "victrola:ui/speakerSelection": {
                "rows": [
                    {
                        "title": "Den + 2",
                        "id": "RINCON_FAKEFAKEFAKE01400",
                        "value": {
                            "type": "sonosGroup",
                            "sonosGroup": {
                                "householdId": "Sonos_secretHOUSE",
                                "leader": {"host": "10.1.2.9"},
                            },
                        },
                    }
                ]
            }
        },
        "events": [],
    }
    out = json.dumps(capture.sanitize(raw, device_ip="10.1.2.3"))
    for secret in (
        "7a0a7a0a",
        "home-wifi",
        "AA:BB:CC:DD:EE",
        "10.1.2.",
        "RINCON_FAKE",
        "Sonos_secretHOUSE",
        "Den",
    ):
        assert secret not in out
    assert "192.0.2.10" in out and "+ 2" in out


def test_fixtures_hold_no_private_values():
    text = "".join(
        (_FIXTURES_DIR / name).read_text()
        for name in ("get_data.json", "get_rows.json", "events.json")
    )
    assert "192.168." not in text
    # Matches up to the enclosing JSON string's own boundary, not just \w+, so
    # a real household id's non-word characters (it carries a dotted suffix)
    # can't hide past where a narrower pattern would stop looking.
    for household in re.findall(r'Sonos_[^"]*', text):
        assert household == "Sonos_EXAMPLE"
    for rincon in re.findall(r"RINCON_\w+", text):
        assert re.fullmatch(r"RINCON_\d{12}01400", rincon)
    for mac in re.findall(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b", text):
        assert re.fullmatch(r"02:00:00:00:00:[0-9A-F]{2}", mac)


def _networkinfo_raw(ips):
    """Build a minimal raw capture whose wireless addresses are exactly ips."""
    return {
        "get_data": {
            "network:info": [
                {
                    "type": "networkInfo",
                    "networkInfo": {
                        "wireless": {
                            "addresses": [{"ip": ip, "protocol": "ipv6"} for ip in ips]
                        }
                    },
                }
            ]
        },
        "get_rows": {},
        "events": [],
    }


def test_sanitize_handles_every_ipv6_compression_shape():
    # Covers the shapes the reviewer named: uncompressed, middle-compressed
    # (fe80::1a2b), leading-compressed (::1), trailing-compressed
    # (2001:db8::), plus the embedded-IPv4 form (::ffff:...) a regex-based
    # discovery pass could mis-split at its dot.
    real_ips = [
        "2001:0db8:0000:0000:0000:0000:0000:0001",
        "fe80::1a2b",
        "::1",
        "2001:db8::",
        "::ffff:198.51.100.7",
    ]
    sanitized = capture.sanitize(_networkinfo_raw(real_ips), device_ip="203.0.113.5")
    addresses = sanitized["get_data"]["network:info"][0]["networkInfo"]["wireless"][
        "addresses"
    ]
    sanitized_ips = [a["ip"] for a in addresses]

    assert len(sanitized_ips) == len(real_ips)
    assert len(set(sanitized_ips)) == len(real_ips)  # each real address, its own slot
    assert not set(sanitized_ips) & set(real_ips)  # none survived verbatim
    for ip in sanitized_ips:
        assert re.fullmatch(r"2001:db8::\d+", ip)


def test_check_sanitized_independently_flags_unredacted_ipv6():
    # A discovery miss, not a wrong-shape replacement: this "sanitized" output
    # was never touched by _sanitize_ipv6 at all, as if some future change
    # broke it. Leading-compressed on purpose: the prior regex-based leak
    # check shared the sanitizer's own blind spot for this exact shape and
    # returned [] here, silently passing a real leak. check_sanitized must
    # now catch it, because its IPv6 check re-derives the answer from the
    # finished output rather than trusting whatever the sanitizer claims to
    # have already done.
    raw = {"get_data": {}, "get_rows": {}, "events": []}
    sanitized = {
        "get_data": {"network:info": [{"ip": "::9999", "protocol": "ipv6"}]},
        "get_rows": {},
        "events": [],
    }
    assert "::9999" in capture.check_sanitized(raw, sanitized)


def _fake_fetchers(monkeypatch):
    monkeypatch.setattr(capture, "_get_data", lambda host, path: [{}])
    monkeypatch.setattr(
        capture, "_get_rows", lambda host, path: {"rows": [], "rowsCount": 0}
    )
    monkeypatch.setattr(capture, "_modify_queue", lambda host, paths: "{fake-queue}")
    monkeypatch.setattr(capture, "_poll_queue", lambda host, queue_id, timeout_s: [])


def test_main_does_not_write_fixtures_when_leaks_detected(monkeypatch, tmp_path):
    _fake_fetchers(monkeypatch)
    monkeypatch.setattr(capture, "check_sanitized", lambda raw, sanitized: ["leak"])
    out_dir = tmp_path / "fixtures"

    exit_code = capture.main(["capture_fixtures.py", "203.0.113.5", str(out_dir)])

    assert exit_code == 1
    assert not out_dir.exists()


def test_main_writes_fixtures_when_clean(monkeypatch, tmp_path):
    _fake_fetchers(monkeypatch)
    out_dir = tmp_path / "fixtures"

    exit_code = capture.main(["capture_fixtures.py", "203.0.113.5", str(out_dir)])

    assert exit_code == 0
    assert {p.name for p in out_dir.iterdir()} == {
        "get_data.json",
        "get_rows.json",
        "events.json",
    }
