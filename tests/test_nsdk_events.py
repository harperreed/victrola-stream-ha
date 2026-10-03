# ABOUTME: Tests for the NSDK event queue: subscribe, poll, and unsubscribe.
# ABOUTME: Pins the modifyQueue/pollQueue request shapes and the seconds-based timeout.
import json
from pathlib import Path

import pytest

from custom_components.victrola_stream.nsdk import NsdkError, NsdkEvent, NsdkValue

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


async def test_poll_returns_empty_list_on_timeout(client):
    queue_id = await client.subscribe(["player:volume"])

    events = await client.poll(queue_id, timeout_s=5)

    assert events == []


async def test_poll_error_body_raises_nsdk_error(client, fake):
    queue_id = await client.subscribe(["player:volume"])
    fake.drop_queues()

    with pytest.raises(NsdkError):
        await client.poll(queue_id, timeout_s=5)


async def test_unsubscribe_sends_paths_in_unsubscribe(client, fake):
    queue_id = await client.subscribe(["player:volume"])

    await client.unsubscribe(queue_id, ["player:volume"])

    assert fake.subscribe_calls[-1] == {
        "queueId": queue_id,
        "subscribe": [],
        "unsubscribe": [{"path": "player:volume", "type": "itemWithValue"}],
    }
