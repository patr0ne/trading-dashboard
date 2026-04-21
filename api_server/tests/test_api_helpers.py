from importlib import util
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
