# ABOUTME: Tests for the sensor platform: Wi-Fi, power state, stream URLs, device card.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.victrola_stream.const import (
    DOMAIN,
    NODE_FIRMWARE,
    NODE_MAC,
    NODE_MCU_FIRMWARE,
    NODE_NETWORK,
    NODE_POWER,
    URL_PATHS,
)
from tests.conftest import entity_id_for, fixture_serial, setup_entry, wait_for

# The device's recorded Wi-Fi signal (tests/fixtures/get_data.json, network:info).
_FIXTURE_SIGNAL_LEVEL = "-62"


def _online_power_target() -> list[dict]:
    """The real powerTarget shape (docs/victrola-nsdk-api.md) with target online."""
    return [
        {
            "type": "powerTarget",
            "powerTarget": {
                "target": "online",
                "reason": "userActivity",
                "nextReason": "none",
                "nextTarget": "none",
            },
        }
    ]


def _flac_url_value() -> list[dict]:
    return [{"type": "string_", "string_": "http://192.0.2.10:44323/stream.flac"}]


async def test_sensors_report_fixture_values(hass, fake):
    # The recorded capture sat in network standby (R8): put the device online
    # with a live stream URL, the shape it reports once it is.
    fake.values[NODE_POWER] = _online_power_target()
    fake.values[URL_PATHS["flac"]] = _flac_url_value()

    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)

    wifi_signal = hass.states.get(entity_id_for(hass, "sensor", serial, "wifi_signal"))
    power_state = hass.states.get(entity_id_for(hass, "sensor", serial, "power_state"))
    stream_url_flac = hass.states.get(
        entity_id_for(hass, "sensor", serial, "stream_url_flac")
    )

    assert wifi_signal.state == _FIXTURE_SIGNAL_LEVEL
    assert power_state.state == "online"
    assert stream_url_flac.state.endswith("/stream.flac")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_missing_node_creates_no_entity(hass, fake):
    del fake.values[NODE_NETWORK]  # answers invalidPath; wifi_signal has no home

    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)

    assert entity_id_for(hass, "sensor", serial, "wifi_signal") is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_device_card(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, serial), entry.entry_id
    )

    assert device is not None
    assert device.manufacturer == "Victrola"
    assert device.model == "Victrola Stream"
    assert device.serial_number == serial
    assert device.sw_version == fake.values[NODE_FIRMWARE][0]["string_"]
    assert device.hw_version == fake.values[NODE_MCU_FIRMWARE][0]["string_"]
    mac = fake.values[NODE_MAC][0]["string_"].lower()
    assert (CONNECTION_NETWORK_MAC, mac) in device.connections

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_unavailable_when_offline(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "sensor", serial, "power_state")
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    fake.offline = True

    await wait_for(lambda: hass.states.get(entity_id).state == STATE_UNAVAILABLE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
