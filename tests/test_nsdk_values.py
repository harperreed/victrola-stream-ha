# ABOUTME: Tests for NSDK typed values, rows, and error classes.
# ABOUTME: Pins the parsing/formatting rules ported from victrola-stream-go.
from custom_components.victrola_stream.nsdk import (
    NsdkConnectionError,
    NsdkError,
    NsdkInvalidPath,
    NsdkRow,
    NsdkValue,
    NsdkWriteRejected,
)


def test_value_parses_i32():
    assert NsdkValue.from_json({"type": "i32_", "i32_": 10}).as_int() == 10


def test_value_empty_object_and_null_are_empty():
    assert NsdkValue.from_json({}).is_empty and NsdkValue.from_json(None).is_empty


def test_value_custom_enum_type_keeps_payload():
    v = NsdkValue.from_json(
        {"type": "forceLowBitrate", "forceLowBitrate": "losslessQuality"}
    )
    assert (v.type, v.payload) == ("forceLowBitrate", "losslessQuality")


def test_value_wrong_accessor_returns_none():
    assert NsdkValue.from_json({"type": "string_", "string_": "x"}).as_int() is None


def test_value_to_json_is_typed_shape():
    assert NsdkValue.of_bool(True).to_json() == {"type": "bool_", "bool_": True}
    assert NsdkValue.of_int(17).to_json() == {"type": "i32_", "i32_": 17}


def test_row_title_strips_html():
    row = NsdkRow.from_json(
        {
            "title": '<div style="margin: -32px 0px 0px 0px">DEFAULT SPEAKER</div>',
            "type": "header",
        }
    )
    assert (
        row.title == "DEFAULT SPEAKER" and row.value.is_empty and row.preferred is False
    )


def test_error_subclasses_carry_name_and_message():
    err = NsdkInvalidPath(
        "CMAbstractWorker::invalidPath", "Node at path 'x' does not exist"
    )
    assert isinstance(err, NsdkError)
    assert (err.name, err.message) == (
        "CMAbstractWorker::invalidPath",
        "Node at path 'x' does not exist",
    )


def test_write_rejected_is_nsdk_error_and_connection_error_is_not():
    assert issubclass(NsdkWriteRejected, NsdkError)
    assert not issubclass(NsdkConnectionError, NsdkError)
