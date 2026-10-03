# ABOUTME: Typed NSDK values, rows, and error types for the Victrola Stream device API.
# ABOUTME: Parses {"type": T, T: value} payloads and getRows entries; no HTTP here.
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_HTML_TAG_RE = re.compile(r"<[^>]*>")

_BOOL_TYPES = frozenset({"bool_"})
_INT_TYPES = frozenset({"i16_", "i32_", "i64_", "u32_", "u64_"})
_FLOAT_TYPES = frozenset({"double_", "flt_"})
_STR_TYPES = frozenset({"string_"})


@dataclass(frozen=True, slots=True)
class NsdkValue:
    """One NSDK typed value, e.g. {"type": "i32_", "i32_": 10}."""

    type: str
    payload: Any

    @classmethod
    def from_json(cls, obj: Any) -> NsdkValue:
        """Map {}, None, and a missing type to EMPTY, else unwrap {"type": T, T: v}."""
        if not obj:
            return EMPTY
        value_type = obj.get("type")
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
        return cls(
            title=_clean_title(obj.get("title") or ""),
            type=obj.get("type"),
            path=obj.get("path"),
            id=obj.get("id"),
            value=NsdkValue.from_json(obj.get("value")),
            preferred=obj.get("preferred") is True,
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
