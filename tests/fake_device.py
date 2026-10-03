# ABOUTME: Stateful fake of the Victrola Stream device's NSDK HTTP API.
# ABOUTME: Built only from recorded fixtures (tests/fixtures/) and verified behaviour.
from __future__ import annotations

import json
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

        base = f"http://{host}"
        aioclient_mock.get(f"{base}/api/getData", side_effect=self._get_data)
        aioclient_mock.get(f"{base}/api/getRows", side_effect=self._get_rows)
        aioclient_mock.post(f"{base}/api/setData", side_effect=self._set_data)

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

    def _check_online(self) -> None:
        if self.offline:
            raise aiohttp.ClientConnectionError("victrola stream device is offline")

    def _invalid_path_body(self, path: str) -> Any:
        """Reuse the one recorded invalidPath capture for any missing path."""
        template = self.values[_INVALID_PATH_KEY]
        text = json.dumps(template).replace(_INVALID_PATH_KEY, path)
        return json.loads(text)
