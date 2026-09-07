"""Unit tests for store helpers that do not need DynamoDB."""

from runway_core.store import _from_dynamo, _to_dynamo
from decimal import Decimal


def test_dynamo_roundtrip_numbers():
    raw = {"a": 1.5, "b": [2.0, {"c": 3}], "d": "x"}
    encoded = _to_dynamo(raw)
    assert isinstance(encoded["a"], Decimal)
    assert isinstance(encoded["b"][0], Decimal)
    decoded = _from_dynamo(encoded)
    assert decoded["a"] == 1.5
    assert decoded["b"][0] == 2
    assert decoded["b"][1]["c"] == 3
    assert decoded["d"] == "x"
