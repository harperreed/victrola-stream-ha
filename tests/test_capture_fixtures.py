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
