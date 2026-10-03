# ABOUTME: NSDK client, typed values, rows, and errors for the Victrola Stream API.
# ABOUTME: Talks getData, getRows, setData; typed writes are read back to confirm.
from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp

_HTML_TAG_RE = re.compile(r"<[^>]*>")

_BOOL_TYPES = frozenset({"bool_"})
_INT_TYPES = frozenset({"i16_", "i32_", "i64_", "u32_", "u64_"})
_FLOAT_TYPES = frozenset({"double_", "flt_"})
_STR_TYPES = frozenset({"string_"})


def _str_or_none(value: Any) -> str | None:
    """value if it is a string, else None: the device's JSON is not trusted."""
    return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True)
class NsdkValue:
    """One NSDK typed value, e.g. {"type": "i32_", "i32_": 10}."""

    type: str
    payload: Any

    @classmethod
    def from_json(cls, obj: Any) -> NsdkValue:
        """Unwrap {"type": T, T: v}. Any other JSON, {} and None too, is EMPTY."""
        if not isinstance(obj, dict):
            return EMPTY
        value_type = _str_or_none(obj.get("type"))
        if not value_type:
            return EMPTY
        return cls(value_type, obj.get(value_type))

    @property
    def is_empty(self) -> bool:
        return self.type == ""

    def as_bool(self) -> bool | None:
        return self.payload if self.type in _BOOL_TYPES else None

    def as_int(self) -> int | None:
        return self.payload if self.type in _INT_TYPES else None

    def as_float(self) -> float | None:
        return self.payload if self.type in _FLOAT_TYPES else None

    def as_str(self) -> str | None:
        return self.payload if self.type in _STR_TYPES else None

    def to_json(self) -> dict[str, Any]:
        return {"type": self.type, self.type: self.payload}

    @classmethod
    def of_bool(cls, v: bool) -> NsdkValue:
        return cls("bool_", v)

    @classmethod
    def of_int(cls, v: int) -> NsdkValue:
        return cls("i32_", v)

    @classmethod
    def of_str(cls, v: str) -> NsdkValue:
        return cls("string_", v)


EMPTY = NsdkValue("", None)


def _clean_title(title: str) -> str:
    """Strip the HTML wrapper some row titles carry, then trim whitespace."""
    return _HTML_TAG_RE.sub("", title).strip()


@dataclass(frozen=True, slots=True)
class NsdkRow:
    """One row from a getRows listing, e.g. a speaker or a settings entry."""

    title: str
    type: str | None
    path: str | None
    id: str | None
    value: NsdkValue
    preferred: bool

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> NsdkRow:
        """Parse one row object; a field of the wrong type reads as absent."""
        return cls(
            title=_clean_title(_str_or_none(obj.get("title")) or ""),
            type=_str_or_none(obj.get("type")),
            path=_str_or_none(obj.get("path")),
            id=_str_or_none(obj.get("id")),
            value=NsdkValue.from_json(obj.get("value")),
            preferred=obj.get("preferred") is True,
        )


@dataclass(frozen=True, slots=True)
class NsdkEvent:
    """One event from a pollQueue reply, e.g. a player:volume change."""

    path: str
    item_type: str
    value: NsdkValue | None

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> NsdkEvent:
        """Parse one pollQueue list item, an object.

        Never raises: a field of the wrong type reads as absent, so a malformed
        item parses with an empty path or item_type, and an itemValue that is
        not a typed value parses as EMPTY. That is the same tolerance
        NsdkRow.from_json gives a malformed row. NsdkClient.poll checks that
        the reply is a list of objects.
        """
        item_value = obj.get("itemValue")
        return cls(
            path=_str_or_none(obj.get("path")) or "",
            item_type=_str_or_none(obj.get("itemType")) or "",
            value=NsdkValue.from_json(item_value) if item_value is not None else None,
        )


class NsdkError(Exception):
    """A device-reported NSDK fault, e.g. CMAbstractWorker::invalidPath."""

    def __init__(self, name: str, message: str = "") -> None:
        super().__init__(f"{name}: {message}" if message else name)
        self.name = name
        self.message = message


class NsdkInvalidPath(NsdkError):
    """Raised when the device reports that a node path does not exist."""


class NsdkWriteRejected(NsdkError):
    """Raised when a write is rejected, or silently ignored, by the device."""


class NsdkConnectionError(Exception):
    """Raised for transport failures, timeouts, and replies with no NSDK error body."""


_TIMEOUT = aiohttp.ClientTimeout(total=10)
# NSDK path query values use ':' and '/' unescaped, matching the device's own
# webclient. yarl's `params=` percent-encodes those, so requests build their
# query string through this instead of passing `params=` to aiohttp.
_QUERY_SAFE_CHARS = "/:@,"


def _query_escape(value: Any) -> str:
    return quote(str(value), safe=_QUERY_SAFE_CHARS)


def _encode_query(params: dict[str, Any]) -> str:
    return "&".join(f"{key}={_query_escape(val)}" for key, val in params.items())


def _queue_item(path: str) -> dict[str, str]:
    return {"path": path, "type": "itemWithValue"}


def _error_from_body(body: Any) -> NsdkError | None:
    """Return the NsdkError an NSDK error body describes, else None."""
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    name = str(error.get("name") or "")
    message = str(error.get("message") or "")
    if name.endswith("invalidPath"):
        return NsdkInvalidPath(name, message)
    return NsdkError(name, message)


def _raise_if_write_rejected(path: str, body: Any) -> None:
    """Raise when the device's setData reply itself rejects the write.

    A literal `false` is an outright rejection. Anything else (a literal
    `true`, or a `{"value": ...}` object) only means the device accepted the
    request; it does not prove the write took effect. For role "value",
    `set_typed` still confirms with a read-back.
    """
    if body is False:
        raise NsdkWriteRejected("write-rejected", f"{path}: device returned false")


class NsdkClient:
    """Talks NSDK HTTP to one Victrola Stream device."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self._host = host

    @property
    def host(self) -> str:
        return self._host

    async def get_value(self, path: str) -> NsdkValue:
        body = await self._get("/api/getData", {"path": path, "roles": "value"})
        if not isinstance(body, list):
            raise NsdkConnectionError(f"getData {path}: expected a list, got {body!r}")
        return NsdkValue.from_json(body[0]) if body else EMPTY

    async def read_nodes(
        self, paths: Iterable[str]
    ) -> tuple[dict[str, NsdkValue], frozenset[str]]:
        """Read many nodes concurrently.

        Returns the values plus the set of paths that answered invalidPath. Any
        other failure (a transport error) cancels the remaining reads and
        raises that one failure directly — never an ExceptionGroup.
        """

        async def read_one(path: str) -> tuple[str, NsdkValue | None]:
            try:
                return path, await self.get_value(path)
            except NsdkInvalidPath:
                return path, None

        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(read_one(path)) for path in paths]
        except* Exception as eg:
            # TaskGroup cancels the other reads and wraps whatever failed in
            # an ExceptionGroup; unwrap it so callers only ever see the
            # NsdkError/NsdkConnectionError that get_value can raise.
            raise eg.exceptions[0] from eg

        results = [task.result() for task in tasks]
        values = {path: value for path, value in results if value is not None}
        missing = frozenset(path for path, value in results if value is None)
        return values, missing

    async def get_rows(
        self, path: str, start: int = 0, end: int = 100
    ) -> list[NsdkRow]:
        body = await self._get(
            "/api/getRows",
            {
                "path": path,
                "roles": "@all",
                "from": start,
                "to": end,
                "type": "structure",
            },
        )
        if not isinstance(body, dict) or not isinstance(body.get("rows"), list):
            raise NsdkConnectionError(
                f"getRows {path}: expected an object with 'rows', got {body!r}"
            )
        # A row that isn't an object names nothing; drop it.
        return [NsdkRow.from_json(row) for row in body["rows"] if isinstance(row, dict)]

    async def set_typed(self, path: str, value: NsdkValue) -> NsdkValue:
        """Write a typed value, then read the node back to confirm it took.

        Raises NsdkWriteRejected when the device rejects the write outright,
        or when the read-back value differs from what was written. There is
        no optimistic state: the read-back is always the return value.
        """
        body = await self._post(
            "/api/setData", {"path": path, "role": "value", "value": value.to_json()}
        )
        _raise_if_write_rejected(path, body)
        readback = await self.get_value(path)
        if readback != value:
            raise NsdkWriteRejected(
                "write-not-applied",
                f"{path}: wrote {value!r}, read back {readback!r}",
            )
        return readback

    async def activate(self, path: str, value: Any) -> None:
        """Fire an action node. Same accept/reject rules as set_typed, no read-back."""
        body = await self._post(
            "/api/setData", {"path": path, "role": "activate", "value": value}
        )
        _raise_if_write_rejected(path, body)

    async def subscribe(self, paths: Iterable[str]) -> str:
        """Create an event queue subscribed to paths; returns the server's queue id."""
        body = await self._modify_queue("", [_queue_item(p) for p in paths], [])
        if not isinstance(body, str) or not body:
            raise NsdkConnectionError(
                f"modifyQueue: expected a queue id string, got {body!r}"
            )
        return body

    async def poll(self, queue_id: str, timeout_s: int) -> list[NsdkEvent]:
        """Long-poll a queue for events. The device's timeout unit is seconds."""
        body = await self._get(
            "/api/event/pollQueue",
            {"queueId": queue_id, "timeout": timeout_s},
            request_timeout=aiohttp.ClientTimeout(total=timeout_s + 10),
        )
        if not isinstance(body, list) or not all(isinstance(i, dict) for i in body):
            raise NsdkConnectionError(
                f"pollQueue: expected a list of objects, got {body!r}"
            )
        return [NsdkEvent.from_json(item) for item in body]

    async def unsubscribe(self, queue_id: str, paths: Iterable[str]) -> None:
        """Drop paths from an existing queue."""
        await self._modify_queue(queue_id, [], [_queue_item(p) for p in paths])

    async def _modify_queue(
        self,
        queue_id: str,
        subscribe: list[dict[str, str]],
        unsubscribe: list[dict[str, str]],
    ) -> Any:
        return await self._post(
            "/api/event/modifyQueue",
            {"queueId": queue_id, "subscribe": subscribe, "unsubscribe": unsubscribe},
        )

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        request_timeout: aiohttp.ClientTimeout | None = None,
    ) -> Any:
        url = f"http://{self._host}{endpoint}?{_encode_query(params)}"
        return await self._send("GET", url, request_timeout=request_timeout)

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        url = f"http://{self._host}{endpoint}"
        return await self._send("POST", url, json_body=payload)

    async def _send(
        self,
        method: str,
        url: str,
        json_body: Any = None,
        request_timeout: aiohttp.ClientTimeout | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method, url, json=json_body, timeout=request_timeout or _TIMEOUT
            ) as resp:
                body = await resp.json()
                error = _error_from_body(body)
                if error is not None:
                    raise error
                if resp.status != 200:
                    raise NsdkConnectionError(f"HTTP {resp.status}: {body!r}")
                return body
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            # ValueError covers a JSON-decode failure (stdlib json.JSONDecodeError
            # and orjson's, both subclass it): a reply the client cannot parse is
            # the same "not a valid NSDK reply" bucket as a non-200 with no error
            # body. Callers must only ever see NsdkError or NsdkConnectionError.
            raise NsdkConnectionError(str(err)) from err
