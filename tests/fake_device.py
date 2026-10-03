# ABOUTME: Stateful fake of the Victrola Stream device's NSDK HTTP API.
# ABOUTME: Built only from recorded fixtures (tests/fixtures/) and verified behaviour.
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import aiohttp
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_INVALID_PATH_KEY = "settings:/victrola/doesNotExist"
# UNVERIFIED: the live tests on 2026-10-02 never captured a reply for an
# unknown or expired queue id. This is the brief's placeholder shape, not a
# recorded payload; NsdkClient treats it like any other NSDK error body.
_QUEUE_NOT_FOUND_BODY = {"error": {"name": "queueNotFound", "message": "unknown queue"}}


def _load_fixture(name: str) -> Any:
    return json.loads((_FIXTURES_DIR / name).read_text())


class FakeVictrola:
    """A stateful stand-in for the device's HTTP API.

    Built only from recorded fixtures and verified behaviour, never invented
    replies. Registers side effects for getData, getRows and setData on the
    given `aioclient_mock` (Task 4 adds the queue endpoints).
    """

    def __init__(
        self, aioclient_mock: AiohttpClientMocker, host: str = "192.0.2.10"
    ) -> None:
        self.host = host
        self.values: dict[str, Any] = _load_fixture("get_data.json")
        self.rows: dict[str, Any] = _load_fixture("get_rows.json")
        self.offline = False
        self.ignore_writes: set[str] = set()
        self.reject_writes: set[str] = set()
        self.set_calls: list[dict[str, Any]] = []
        self.raw_replies: dict[str, str] = {}
        self.subscribe_calls: list[dict[str, Any]] = []
        self.poll_wait_s: float = 0.01
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._dropped_queues: set[str] = set()

        base = f"http://{host}"
        aioclient_mock.get(f"{base}/api/getData", side_effect=self._get_data)
        aioclient_mock.get(f"{base}/api/getRows", side_effect=self._get_rows)
        aioclient_mock.post(f"{base}/api/setData", side_effect=self._set_data)
        aioclient_mock.post(
            f"{base}/api/event/modifyQueue", side_effect=self._modify_queue
        )
        aioclient_mock.get(f"{base}/api/event/pollQueue", side_effect=self._poll_queue)

    async def _get_data(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        self._check_online()
        path = url.query["path"]
        if path in self.raw_replies:
            return AiohttpClientMockResponse(
                method=method, url=url, text=self.raw_replies[path]
            )
        if path in self.values and path != _INVALID_PATH_KEY:
            return AiohttpClientMockResponse(
                method=method, url=url, json=self.values[path]
            )
        return AiohttpClientMockResponse(
            method=method, url=url, status=500, json=self._invalid_path_body(path)
        )

    async def _get_rows(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        self._check_online()
        path = url.query["path"]
        if path in self.rows:
            return AiohttpClientMockResponse(
                method=method, url=url, json=self.rows[path]
            )
        return AiohttpClientMockResponse(
            method=method, url=url, status=500, json=self._invalid_path_body(path)
        )

    async def _set_data(
        self, method: str, url: URL, data: dict[str, Any]
    ) -> AiohttpClientMockResponse:
        self._check_online()
        path = data["path"]
        role = data["role"]
        value = data["value"]
        self.set_calls.append({"path": path, "role": role, "value": value})

        if role == "activate":
            return AiohttpClientMockResponse(method=method, url=url, json=True)

        if path in self.reject_writes:
            return AiohttpClientMockResponse(method=method, url=url, json=False)
        if path in self.ignore_writes:
            current = self.values.get(path, [{}])[0]
            return AiohttpClientMockResponse(
                method=method, url=url, json={"value": current, "timestamp": 1}
            )

        self.values[path] = [value]
        if path.startswith("player:"):
            return AiohttpClientMockResponse(method=method, url=url, json=True)
        return AiohttpClientMockResponse(
            method=method, url=url, json={"value": value, "timestamp": 1}
        )

    async def _modify_queue(
        self, method: str, url: URL, data: dict[str, Any]
    ) -> AiohttpClientMockResponse:
        self._check_online()
        self.subscribe_calls.append(data)
        queue_id = data["queueId"]
        if not queue_id:
            queue_id = f"{{{uuid.uuid4()}}}"
            self._queues[queue_id] = asyncio.Queue()
        return AiohttpClientMockResponse(method=method, url=url, json=queue_id)

    async def _poll_queue(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        self._check_online()
        queue_id = url.query["queueId"]
        if queue_id in self._dropped_queues or queue_id not in self._queues:
            return AiohttpClientMockResponse(
                method=method, url=url, json=_QUEUE_NOT_FOUND_BODY
            )
        queue = self._queues[queue_id]
        try:
            event = await asyncio.wait_for(queue.get(), timeout=self.poll_wait_s)
            events = [event]
        except TimeoutError:
            events = []
        return AiohttpClientMockResponse(method=method, url=url, json=events)

    def push_event(self, path: str, value_json: dict[str, Any]) -> None:
        """Record a value change and queue its event for every live queue."""
        self.values[path] = [value_json]
        event = {
            "itemType": "update",
            "path": path,
            "itemValue": value_json,
            "rowsEvents": [],
        }
        for queue_id, queue in self._queues.items():
            if queue_id not in self._dropped_queues:
                queue.put_nowait(event)

    def drop_queues(self) -> None:
        """Make every current queue id answer pollQueue as unknown.

        UNVERIFIED: see _QUEUE_NOT_FOUND_BODY above.
        """
        self._dropped_queues.update(self._queues)

    def _check_online(self) -> None:
        if self.offline:
            raise aiohttp.ClientConnectionError("victrola stream device is offline")

    def _invalid_path_body(self, path: str) -> Any:
        """Reuse the one recorded invalidPath capture for any missing path."""
        template = self.values[_INVALID_PATH_KEY]
        text = json.dumps(template).replace(_INVALID_PATH_KEY, path)
        return json.loads(text)
