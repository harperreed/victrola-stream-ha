# ABOUTME: Tests for NsdkClient against FakeVictrola: reads, typed writes, rows.
# ABOUTME: Pins read-back confirmation and the unescaped-path-character query format.
import pytest

from custom_components.victrola_stream import const
from custom_components.victrola_stream.nsdk import (
    NsdkConnectionError,
    NsdkInvalidPath,
    NsdkValue,
    NsdkWriteRejected,
)

# The `fake` and `client` fixtures live in tests/conftest.py, shared with
# tests/test_nsdk_events.py.


async def test_get_value_parses_typed_value(client):
    value = await client.get_value(const.NODE_AUTOPLAY)

    assert value.as_bool() is True


async def test_get_value_keeps_path_characters_unescaped(client, aioclient_mock):
    await client.get_value("settings:/victrola/lightBrightness")

    last_url = str(aioclient_mock.mock_calls[-1][1])
    assert "path=settings:/victrola/lightBrightness" in last_url


async def test_get_value_invalid_path_raises(client):
    with pytest.raises(NsdkInvalidPath):
        await client.get_value("settings:/victrola/nope")


async def test_read_nodes_splits_missing_paths(client):
    values, missing = await client.read_nodes(
        [const.NODE_AUTOPLAY, "settings:/victrola/nope"]
    )

    assert values[const.NODE_AUTOPLAY].as_bool() is True
    assert missing == {"settings:/victrola/nope"}


async def test_offline_raises_connection_error(client, fake):
    fake.offline = True

    with pytest.raises(NsdkConnectionError):
        await client.get_value(const.NODE_AUTOPLAY)


async def test_get_value_malformed_json_raises_connection_error(client, fake):
    fake.raw_replies[const.NODE_AUTOPLAY] = "not json"

    with pytest.raises(NsdkConnectionError):
        await client.get_value(const.NODE_AUTOPLAY)


async def test_get_value_wrong_shape_raises_connection_error(client, fake):
    fake.values[const.NODE_AUTOPLAY] = {}  # object, not a list, and no "error" key

    with pytest.raises(NsdkConnectionError):
        await client.get_value(const.NODE_AUTOPLAY)


async def test_get_rows_wrong_shape_raises_connection_error(client, fake):
    fake.rows[const.SPEAKERS_PATH] = []  # a list, not an object with "rows"

    with pytest.raises(NsdkConnectionError):
        await client.get_rows(const.SPEAKERS_PATH)


async def test_read_nodes_transport_failure_raises_connection_error(client, fake):
    fake.offline = True

    with pytest.raises(NsdkConnectionError) as exc_info:
        await client.read_nodes([const.NODE_AUTOPLAY, const.NODE_KNOB_BRIGHTNESS])

    assert not isinstance(exc_info.value, ExceptionGroup)


async def test_set_typed_sends_typed_body_and_reads_back(client, fake):
    got = await client.set_typed(
        "settings:/victrola/lightBrightness", NsdkValue.of_int(17)
    )

    assert fake.set_calls[-1] == {
        "path": "settings:/victrola/lightBrightness",
        "role": "value",
        "value": {"type": "i32_", "i32_": 17},
    }
    assert got == NsdkValue.of_int(17)


async def test_set_typed_raises_when_readback_differs(client, fake):
    fake.ignore_writes.add(const.NODE_KNOB_BRIGHTNESS)

    with pytest.raises(NsdkWriteRejected):
        await client.set_typed(const.NODE_KNOB_BRIGHTNESS, NsdkValue.of_int(99))


async def test_set_typed_raises_on_false_reply(client, fake):
    fake.reject_writes.add(const.NODE_KNOB_BRIGHTNESS)

    with pytest.raises(NsdkWriteRejected):
        await client.set_typed(const.NODE_KNOB_BRIGHTNESS, NsdkValue.of_int(99))


async def test_activate_posts_activate_role(client, fake):
    await client.activate(const.NODE_REBOOT, {})

    assert fake.set_calls[-1] == {
        "path": const.NODE_REBOOT,
        "role": "activate",
        "value": {},
    }


async def test_get_rows_parses_speakers(client):
    rows = await client.get_rows(const.SPEAKERS_PATH)

    speaker_rows = [row for row in rows if row.id is not None]
    assert len(speaker_rows) == 13
    assert sum(row.preferred for row in speaker_rows) == 1
    assert all("<" not in row.title for row in rows if row.title)
