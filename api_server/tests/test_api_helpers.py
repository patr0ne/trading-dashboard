import asyncio
from importlib import util
import json
from pathlib import Path

API_MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"
API_MODULE_SPEC = util.spec_from_file_location("api_server_main", API_MAIN_PATH)
assert API_MODULE_SPEC is not None and API_MODULE_SPEC.loader is not None
API_MODULE = util.module_from_spec(API_MODULE_SPEC)
API_MODULE_SPEC.loader.exec_module(API_MODULE)

_decode_pubsub_data = API_MODULE._decode_pubsub_data
_extract_updated_at_ms = API_MODULE._extract_updated_at_ms
_extract_open_time_ms = API_MODULE._extract_open_time_ms
_ticker_identity = API_MODULE._ticker_identity
_kline_identity = API_MODULE._kline_identity
_redis_key = API_MODULE._redis_key
_fetch_kline_history = API_MODULE._fetch_kline_history
_merge_kline_history_items = API_MODULE._merge_kline_history_items


def test_decode_pubsub_data_handles_bytes_and_string() -> None:
    assert _decode_pubsub_data(b"hello") == "hello"
    assert _decode_pubsub_data("world") == "world"


def test_extract_updated_at_ms_handles_valid_and_invalid_values() -> None:
    assert _extract_updated_at_ms({"updated_at_ms": "123"}) == 123
    assert _extract_updated_at_ms({"updated_at_ms": 456}) == 456
    assert _extract_updated_at_ms({"updated_at_ms": "bad"}) == 0
    assert _extract_updated_at_ms({}) == 0


def test_extract_open_time_ms_uses_open_time_or_fallback() -> None:
    assert _extract_open_time_ms({"open_time_ms": "456", "updated_at_ms": "123"}) == 456
    assert _extract_open_time_ms({"updated_at_ms": "123"}) == 123


def test_ticker_identity_uses_source_and_symbol() -> None:
    assert _ticker_identity({"source": "bybit", "symbol": "BTCUSDT"}) == "bybit:BTCUSDT"
    assert _ticker_identity({"source": "binance"}) is None


def test_kline_identity_requires_interval() -> None:
    assert _kline_identity({"source": "bybit", "symbol": "BTCUSDT", "interval": "1m"}) == "bybit:BTCUSDT:1m"
    assert _kline_identity({"source": "bybit", "symbol": "BTCUSDT"}) is None


def test_redis_key_includes_optional_interval() -> None:
    assert _redis_key("ticker", "bybit", "BTCUSDT") == "ticker:bybit:BTCUSDT"
    assert _redis_key("orderbook", "bybit", "BTCUSDT") == "orderbook:bybit:BTCUSDT"
    assert _redis_key("kline", "bybit", "BTCUSDT", "1m") == "kline:bybit:BTCUSDT:1m"
    assert _redis_key("kline_history", "binance", "ETHUSDT", "1m") == "kline_history:binance:ETHUSDT:1m"


def test_fetch_kline_history_supports_before_open_time_pagination() -> None:
    class FakeRedis:
        async def lrange(self, key: str, start: int, stop: int) -> list[str]:
            assert key == "kline_history:binance:BTCUSDT:1m"
            assert start == 0
            assert stop == -1
            return [
                json.dumps({"open_time_ms": "4000", "updated_at_ms": "4000", "close": "4"}),
                json.dumps({"open_time_ms": "3000", "updated_at_ms": "3000", "close": "3"}),
                json.dumps({"open_time_ms": "2000", "updated_at_ms": "2000", "close": "2"}),
                json.dumps({"open_time_ms": "1000", "updated_at_ms": "1000", "close": "1"}),
            ]

    result = asyncio.run(
        _fetch_kline_history(
            FakeRedis(),
            source="binance",
            symbol="BTCUSDT",
            interval="1m",
            limit=2,
            before_open_time_ms=3000,
        )
    )

    assert [item["open_time_ms"] for item in result] == ["1000", "2000"]


def test_merge_kline_history_items_deduplicates_and_sorts_by_open_time() -> None:
    merged = _merge_kline_history_items(
        [
            {"open_time_ms": "3000", "updated_at_ms": "3000", "close": "3"},
            {"open_time_ms": "2000", "updated_at_ms": "2000", "close": "2"},
        ],
        [
            {"open_time_ms": "2000", "updated_at_ms": "2100", "close": "2.1"},
            {"open_time_ms": "1000", "updated_at_ms": "1000", "close": "1"},
        ],
    )

    assert [item["open_time_ms"] for item in merged] == ["1000", "2000", "3000"]
    assert next(item for item in merged if item["open_time_ms"] == "2000")["close"] == "2.1"
