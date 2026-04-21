from importlib import util
from pathlib import Path

INGESTER_MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"
INGESTER_MODULE_SPEC = util.spec_from_file_location("ingester_main", INGESTER_MAIN_PATH)
assert INGESTER_MODULE_SPEC is not None and INGESTER_MODULE_SPEC.loader is not None
INGESTER_MODULE = util.module_from_spec(INGESTER_MODULE_SPEC)
INGESTER_MODULE_SPEC.loader.exec_module(INGESTER_MODULE)

_parse_bybit_ticker_message = INGESTER_MODULE._parse_bybit_ticker_message
_parse_bybit_trade_message = INGESTER_MODULE._parse_bybit_trade_message
_parse_bybit_orderbook_message = INGESTER_MODULE._parse_bybit_orderbook_message
_parse_bybit_kline_message = INGESTER_MODULE._parse_bybit_kline_message
_parse_binance_ticker_message = INGESTER_MODULE._parse_binance_ticker_message
_parse_binance_trade_message = INGESTER_MODULE._parse_binance_trade_message
_parse_binance_orderbook_message = INGESTER_MODULE._parse_binance_orderbook_message
_parse_binance_kline_message = INGESTER_MODULE._parse_binance_kline_message
_build_binance_stream_url = INGESTER_MODULE._build_binance_stream_url
_ticker_key = INGESTER_MODULE._ticker_key
_trade_key = INGESTER_MODULE._trade_key
_orderbook_key = INGESTER_MODULE._orderbook_key
_kline_key = INGESTER_MODULE._kline_key
_kline_history_key = INGESTER_MODULE._kline_history_key


def test_parse_bybit_ticker_message_returns_normalized_ticker() -> None:
    payload = {
        "topic": "tickers.BTCUSDT",
        "data": {
            "lastPrice": "69000.1",
            "price24hPcnt": "0.0123",
            "volume24h": "1234.56",
        },
    }

    result = _parse_bybit_ticker_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == "69000.1"
    assert result["change24h"] == "0.0123"
    assert result["volume24h"] == "1234.56"
    assert result["source"] == "bybit"
    assert "updated_at_ms" in result


def test_parse_bybit_ticker_message_skips_invalid_payload() -> None:
    assert _parse_bybit_ticker_message({"topic": "other.BTCUSDT", "data": {}}) is None
    assert _parse_bybit_ticker_message({"topic": "tickers.BTCUSDT", "data": {}}) is None
    assert _parse_bybit_ticker_message({"topic": "tickers.BTCUSDT", "data": "not-object"}) is None


def test_parse_binance_ticker_message_returns_normalized_ticker() -> None:
    payload = {
        "stream": "btcusdt@ticker",
        "data": {
            "s": "BTCUSDT",
            "c": "70000.5",
            "P": "1.23",
            "v": "42.5",
            "E": 1712750000123,
        },
    }

    result = _parse_binance_ticker_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == "70000.5"
    assert result["change24h"] == "1.23"
    assert result["volume24h"] == "42.5"
    assert result["source"] == "binance"
    assert result["updated_at_ms"] == "1712750000123"


def test_parse_bybit_trade_message_returns_normalized_trade() -> None:
    payload = {
        "topic": "publicTrade.BTCUSDT",
        "data": [{"p": "70000.1", "v": "0.05", "S": "Buy", "T": 1712751234000}],
    }

    result = _parse_bybit_trade_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == "70000.1"
    assert result["size"] == "0.05"
    assert result["side"] == "buy"
    assert result["source"] == "bybit"
    assert result["updated_at_ms"] == "1712751234000"


def test_parse_binance_trade_message_returns_normalized_trade() -> None:
    payload = {
        "stream": "btcusdt@trade",
        "data": {"s": "BTCUSDT", "p": "70001.0", "q": "0.12", "m": True, "T": 1712751235000},
    }

    result = _parse_binance_trade_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == "70001.0"
    assert result["size"] == "0.12"
    assert result["side"] == "sell"
    assert result["source"] == "binance"
    assert result["updated_at_ms"] == "1712751235000"


def test_parse_binance_trade_message_supports_string_bool_maker_flag() -> None:
    payload = {
        "stream": "btcusdt@trade",
        "data": {"s": "BTCUSDT", "p": "70001.0", "q": "0.12", "m": "false", "T": 1712751235001},
    }

    result = _parse_binance_trade_message(payload)

    assert result is not None
    assert result["side"] == "buy"


def test_parse_trade_message_skips_unknown_side() -> None:
    bybit_payload = {
        "topic": "publicTrade.BTCUSDT",
        "data": [{"p": "70000.1", "v": "0.05", "S": "UNKNOWN", "T": 1712751234000}],
    }
    binance_payload = {
        "stream": "btcusdt@trade",
        "data": {"s": "BTCUSDT", "p": "70001.0", "q": "0.12", "m": "???", "T": 1712751235000},
    }

    assert _parse_bybit_trade_message(bybit_payload) is None
    assert _parse_binance_trade_message(binance_payload) is None


def test_parse_bybit_orderbook_message_returns_normalized_payload() -> None:
    payload = {
        "topic": "orderbook.50.BTCUSDT",
        "ts": 1712751239000,
        "data": {
            "b": [["70000.1", "1.2"], ["69999.5", "0.8"]],
            "a": [["70001.2", "0.4"], ["70002.0", "1.0"]],
        },
    }

    result = _parse_bybit_orderbook_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["source"] == "bybit"
    assert result["updated_at_ms"] == "1712751239000"
    assert result["bids_json"].startswith("[")
    assert result["asks_json"].startswith("[")


def test_parse_bybit_orderbook_message_accepts_any_depth_topic() -> None:
    payload = {
        "topic": "orderbook.1.BTCUSDT",
        "data": {
            "b": [["70000.1", "1.2"]],
            "a": [["70001.2", "0.4"]],
        },
    }

    result = _parse_bybit_orderbook_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"


def test_parse_binance_orderbook_message_supports_partial_depth_payload() -> None:
    payload = {
        "stream": "btcusdt@depth20@1000ms",
        "data": {
            "lastUpdateId": 10,
            "bids": [["70000.1", "1.2"], ["69999.5", "0.8"]],
            "asks": [["70001.2", "0.4"], ["70002.0", "1.0"]],
            "E": 1712751240000,
        },
    }

    result = _parse_binance_orderbook_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["source"] == "binance"
    assert result["updated_at_ms"] == "1712751240000"
    assert result["bids_json"].startswith("[")
    assert result["asks_json"].startswith("[")


def test_parse_bybit_kline_message_returns_normalized_kline() -> None:
    payload = {
        "topic": "kline.1.BTCUSDT",
        "data": [{"open": "70000", "high": "70100", "low": "69900", "close": "70050", "volume": "120.5", "end": 1712751260000}],
    }

    result = _parse_bybit_kline_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["interval"] == "1m"
    assert result["open"] == "70000"
    assert result["high"] == "70100"
    assert result["low"] == "69900"
    assert result["close"] == "70050"
    assert result["volume"] == "120.5"
    assert result["source"] == "bybit"
    assert result["open_time_ms"] == "1712751260000"
    assert result["updated_at_ms"] == "1712751260000"


def test_parse_binance_kline_message_returns_normalized_kline() -> None:
    payload = {
        "stream": "btcusdt@kline_1m",
        "data": {
            "s": "BTCUSDT",
            "E": 1712751261000,
            "k": {
                "t": 1712751200000,
                "i": "1m",
                "o": "70010",
                "h": "70200",
                "l": "69950",
                "c": "70120",
                "v": "99.9",
                "T": 1712751260000,
            },
        },
    }

    result = _parse_binance_kline_message(payload)

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["interval"] == "1m"
    assert result["open"] == "70010"
    assert result["high"] == "70200"
    assert result["low"] == "69950"
    assert result["close"] == "70120"
    assert result["volume"] == "99.9"
    assert result["source"] == "binance"
    assert result["open_time_ms"] == "1712751200000"
    assert result["updated_at_ms"] == "1712751260000"


def test_parse_bybit_kline_message_maps_hourly_interval() -> None:
    payload = {
        "topic": "kline.60.BTCUSDT",
        "data": [{"open": "70000", "high": "70100", "low": "69900", "close": "70050", "volume": "120.5", "end": 1712751260000}],
    }

    result = _parse_bybit_kline_message(payload)

    assert result is not None
    assert result["interval"] == "1h"


def test_build_binance_stream_url_contains_all_supported_kline_intervals() -> None:
    stream_url = _build_binance_stream_url()

    assert "@depth20@1000ms" in stream_url
    assert "@kline_1m" in stream_url
    assert "@kline_5m" in stream_url
    assert "@kline_15m" in stream_url
    assert "@kline_1h" in stream_url


def test_ticker_key_contains_source_and_symbol() -> None:
    ticker = {"source": "binance", "symbol": "BTCUSDT"}
    assert _ticker_key(ticker) == "ticker:binance:BTCUSDT"


def test_trade_and_kline_keys_include_source_symbol_interval() -> None:
    trade = {"source": "binance", "symbol": "BTCUSDT"}
    orderbook = {"source": "binance", "symbol": "BTCUSDT"}
    kline = {"source": "bybit", "symbol": "ETHUSDT", "interval": "1m"}

    assert _trade_key(trade) == "trade:binance:BTCUSDT"
    assert _orderbook_key(orderbook) == "orderbook:binance:BTCUSDT"
    assert _kline_key(kline) == "kline:bybit:ETHUSDT:1m"
    assert _kline_history_key(kline) == "kline_history:bybit:ETHUSDT:1m"
