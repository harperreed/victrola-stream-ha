# ABOUTME: Tests for the NSDK event queue: subscribe, poll, and unsubscribe.
# ABOUTME: Pins the modifyQueue/pollQueue request shapes and the seconds-based timeout.
import json
from pathlib import Path

import pytest

from custom_components.victrola_stream.nsdk import (
    EMPTY,
    NsdkConnectionError,
    NsdkEvent,
    NsdkValue,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


async def test_subscribe_returns_server_queue_id(client, fake):
    queue_id = await client.subscribe(["player:volume"])

    assert fake.subscribe_calls[-1] == {
        "queueId": "",
        "subscribe": [{"path": "player:volume", "type": "itemWithValue"}],
        "unsubscribe": [],
    }
    assert queue_id.startswith("{") and queue_id.endswith("}")


async def test_poll_sends_seconds_timeout_and_queue_id(client, aioclient_mock):
    queue_id = await client.subscribe(["player:volume"])

    await client.poll(queue_id, timeout_s=25)

    url = aioclient_mock.mock_calls[-1][1]
    assert url.query["timeout"] == "25"
    assert url.query["queueId"] == queue_id


async def test_poll_parses_recorded_event(client, fake):
    events_fixture = json.loads((_FIXTURES_DIR / "events.json").read_text())
    recorded_event = events_fixture[1][0]  # the player:volume event, R5
    queue_id = await client.subscribe(["player:volume"])
    fake.push_event(recorded_event["path"], recorded_event["itemValue"])

    events = await client.poll(queue_id, timeout_s=5)

    assert events == [
        NsdkEvent(path="player:volume", item_type="update", value=NsdkValue("i32_", 0))
    ]


def test_event_fields_of_the_wrong_type_read_as_absent():
    event = NsdkEvent.from_json({"path": 7, "itemType": None, "itemValue": "garbage"})

    assert event == NsdkEvent(path="", item_type="", value=EMPTY)


async def test_poll_item_that_is_not_an_object_raises_connection_error(client, fake):
    queue_id = await client.subscribe(["player:volume"])
    fake.push_raw_event("garbage")

    with pytest.raises(NsdkConnectionError):
        await client.poll(queue_id, timeout_s=5)


async def test_poll_returns_empty_list_on_timeout(client):
    queue_id = await client.subscribe(["player:volume"])

    events = await client.poll(queue_id, timeout_s=5)

    assert events == []


async def test_poll_dropped_queue_raises_nsdk_connection_error(client, fake):
    # The device's real reply (Ruling R13 probe 1) is a non-JSON HTTP 400,
    # which NsdkClient cannot parse as an NSDK error body; it surfaces the
    # same as any other reply it cannot read.
    queue_id = await client.subscribe(["player:volume"])
    fake.drop_queues()

    with pytest.raises(NsdkConnectionError):
        await client.poll(queue_id, timeout_s=5)


async def test_unsubscribe_sends_paths_in_unsubscribe(client, fake):
    queue_id = await client.subscribe(["player:volume"])

    await client.unsubscribe(queue_id, ["player:volume"])

    assert fake.subscribe_calls[-1] == {
        "queueId": queue_id,
        "subscribe": [],
        "unsubscribe": [{"path": "player:volume", "type": "itemWithValue"}],
    }
