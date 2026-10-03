# ABOUTME: Tests for the sensor platform: Wi-Fi, power state, stream URLs, device card.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
import logging

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.victrola_stream.const import (
    DOMAIN,
    NODE_FIRMWARE,
    NODE_MAC,
    NODE_MCU_FIRMWARE,
    NODE_NETWORK,
    NODE_POWER,
    NODE_RSSI_EVENT,
    URL_PATHS,
)
from custom_components.victrola_stream.nsdk import NsdkValue
from tests.conftest import entity_id_for, fixture_serial, setup_entry, wait_for

# The device's recorded Wi-Fi signal (tests/fixtures/get_data.json, network:info).
_FIXTURE_SIGNAL_LEVEL = "-62"
_SENSOR_MODULE = "custom_components.victrola_stream.sensor"


def _power_target(target: str) -> dict:
    """The real powerTarget shape (docs/victrola-nsdk-api.md) with this target."""
    return {
        "type": "powerTarget",
        "powerTarget": {
            "target": target,
            "reason": "userActivity",
            "nextReason": "none",
            "nextTarget": "none",
        },
    }


def _online_power_target() -> list[dict]:
    return [_power_target("online")]


def _flac_url_value() -> list[dict]:
    return [{"type": "string_", "string_": "http://192.0.2.10:44323/stream.flac"}]


async def test_sensors_report_fixture_values(hass, fake):
    # R8: the recorded capture sat in network standby with blank stream URLs.
    # The fixture is untouched here; this is the device's actual recorded state.
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)

    wifi_signal = hass.states.get(entity_id_for(hass, "sensor", serial, "wifi_signal"))
    power_state = hass.states.get(entity_id_for(hass, "sensor", serial, "power_state"))
    stream_url_hls = hass.states.get(
        entity_id_for(hass, "sensor", serial, "stream_url_hls")
    )
    stream_url_mp3 = hass.states.get(
        entity_id_for(hass, "sensor", serial, "stream_url_mp3")
    )
    stream_url_flac = hass.states.get(
        entity_id_for(hass, "sensor", serial, "stream_url_flac")
    )

    assert wifi_signal.state == _FIXTURE_SIGNAL_LEVEL
    assert power_state.state == "network_standby"
    assert stream_url_hls.state == STATE_UNKNOWN
    assert stream_url_mp3.state == STATE_UNKNOWN
    assert stream_url_flac.state == STATE_UNKNOWN

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors_report_online_values(hass, fake):
    # R8: override the recorded standby snapshot with the device's online
    # shape (real powerTarget/URL payloads), set before setup.
    fake.values[NODE_POWER] = _online_power_target()
    fake.values[URL_PATHS["flac"]] = _flac_url_value()

    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)

    power_state = hass.states.get(entity_id_for(hass, "sensor", serial, "power_state"))
    stream_url_flac = hass.states.get(
        entity_id_for(hass, "sensor", serial, "stream_url_flac")
    )

    assert power_state.state == "online"
    assert stream_url_flac.state.endswith("/stream.flac")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_unknown_power_target_warns_once_per_value(hass, fake, caplog):
    # Neither target is one the sensor maps; both are made up for this test.
    fake.values[NODE_POWER] = [_power_target("hibernating")]
    entry = await setup_entry(hass, fake)
    coordinator = entry.runtime_data
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    def target() -> str:
        return coordinator.data.value(NODE_POWER).payload["target"]

    for _ in range(3):  # each update makes every entity write its state again
        coordinator.async_update_listeners()
    fake.push_event(NODE_POWER, _power_target("dozing"))
    await wait_for(lambda: target() == "dozing")
    coordinator.async_update_listeners()
    fake.push_event(NODE_POWER, _power_target("hibernating"))
    await wait_for(lambda: target() == "hibernating")

    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == _SENSOR_MODULE and record.levelno == logging.WARNING
    ] == [
        "Unknown power target: 'hibernating'",
        "Unknown power target: 'dozing'",
    ]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_wifi_signal_follows_an_rssi_event(hass, fake):
    # The device sent no RSSI event in a ~65 s live probe, so its shape is
    # unverified; an i32_ in dBm is what this sensor expects.
    entry = await setup_entry(hass, fake)
    entity_id = entity_id_for(hass, "sensor", fixture_serial(fake), "wifi_signal")
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    fake.push_event(NODE_RSSI_EVENT, {"type": "i32_", "i32_": -55})

    await wait_for(lambda: hass.states.get(entity_id).state == "-55")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_wifi_signal_falls_back_when_an_rssi_event_is_not_an_int(hass, fake):
    entry = await setup_entry(hass, fake)
    entity_id = entity_id_for(hass, "sensor", fixture_serial(fake), "wifi_signal")
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed
    rssi = {"type": "double_", "double_": -55.0}

    fake.push_event(NODE_RSSI_EVENT, rssi)

    coordinator = entry.runtime_data
    await wait_for(
        lambda: coordinator.data.value(NODE_RSSI_EVENT) == NsdkValue.from_json(rssi)
    )
    assert hass.states.get(entity_id).state == _FIXTURE_SIGNAL_LEVEL

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
