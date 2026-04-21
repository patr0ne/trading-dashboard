import asyncio
import json
import logging
import os
from time import perf_counter
import time
from typing import Any

import httpx
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import redis.asyncio as redis
from redis.exceptions import RedisError
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

LOGGER = logging.getLogger("market-ingester")

BYBIT_WS_URL = os.getenv("BYBIT_WS_URL", "wss://stream.bybit.com/v5/public/spot")
BINANCE_WS_URL = os.getenv("BINANCE_WS_URL", "wss://stream.binance.com:9443/stream")
BYBIT_HTTP_URL = os.getenv("BYBIT_HTTP_URL", "https://api.bybit.com")
BINANCE_HTTP_URL = os.getenv("BINANCE_HTTP_URL", "https://api.binance.com")
SYMBOLS = [symbol.strip().upper() for symbol in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if symbol.strip()]
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TICKER_CHANNEL = os.getenv("TICKER_CHANNEL", "ticker_updates")
TICKER_KEY_PREFIX = os.getenv("TICKER_KEY_PREFIX", "ticker")
TRADE_CHANNEL = os.getenv("TRADE_CHANNEL", "trade_updates")
TRADE_KEY_PREFIX = os.getenv("TRADE_KEY_PREFIX", "trade")
ORDERBOOK_CHANNEL = os.getenv("ORDERBOOK_CHANNEL", "orderbook_updates")
ORDERBOOK_KEY_PREFIX = os.getenv("ORDERBOOK_KEY_PREFIX", "orderbook")
KLINE_CHANNEL = os.getenv("KLINE_CHANNEL", "kline_updates")
KLINE_KEY_PREFIX = os.getenv("KLINE_KEY_PREFIX", "kline")
KLINE_HISTORY_KEY_PREFIX = os.getenv("KLINE_HISTORY_KEY_PREFIX", "kline_history")
KLINE_HISTORY_LIMIT = int(os.getenv("KLINE_HISTORY_LIMIT", "1000"))
ORDERBOOK_LEVELS = int(os.getenv("ORDERBOOK_LEVELS", "20"))
BYBIT_ORDERBOOK_TOPIC_DEPTH = os.getenv("BYBIT_ORDERBOOK_TOPIC_DEPTH", "50")
BINANCE_ORDERBOOK_STREAM_LEVELS = os.getenv("BINANCE_ORDERBOOK_STREAM_LEVELS", "20")
BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS = float(os.getenv("BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS", "2.5"))
KLINE_INTERVALS = [value.strip() for value in os.getenv("KLINE_INTERVALS", "1m,5m,15m,1h").split(",") if value.strip()]
BYBIT_KLINE_TOPIC_INTERVALS = [
    value.strip() for value in os.getenv("BYBIT_KLINE_TOPIC_INTERVALS", "1,5,15,60").split(",") if value.strip()
]
RECONNECT_DELAY_SECONDS = float(os.getenv("RECONNECT_DELAY_SECONDS", "3"))
INGESTER_METRICS_PORT = int(os.getenv("INGESTER_METRICS_PORT", "9108"))

INGESTER_PUBLISHED_EVENTS_TOTAL = Counter(
    "trading_ingester_published_events_total",
    "Total number of events published by ingester to Redis channels",
    ("channel", "source", "symbol"),
)
INGESTER_WS_RECONNECTS_TOTAL = Counter(
    "trading_ingester_ws_reconnects_total",
    "Total websocket reconnect attempts by source",
    ("source",),
)
INGESTER_ACTIVE_STREAMS = Gauge(
    "trading_ingester_active_streams",
    "Current active websocket streams by source",
    ("source",),
)
INGESTER_WARMUP_DURATION_SECONDS = Histogram(
    "trading_ingester_warmup_duration_seconds",
    "Warmup duration in seconds by stage",
    ("stage",),
)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_BYBIT = _env_flag("ENABLE_BYBIT", True)
ENABLE_BINANCE = _env_flag("ENABLE_BINANCE", True)

CANONICAL_TO_BYBIT_INTERVAL: dict[str, str] = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
}
BYBIT_TO_CANONICAL_INTERVAL: dict[str, str] = {value: key for key, value in CANONICAL_TO_BYBIT_INTERVAL.items()}


def _normalize_kline_intervals(values: list[str]) -> list[str]:
    normalized = [value.strip().lower() for value in values if value.strip()]
    return [value for value in normalized if value in CANONICAL_TO_BYBIT_INTERVAL]


def _normalize_bybit_topic_intervals(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values if value.strip()]
    return [value for value in normalized if value in BYBIT_TO_CANONICAL_INTERVAL]


KLINE_INTERVALS = _normalize_kline_intervals(KLINE_INTERVALS)
BYBIT_KLINE_TOPIC_INTERVALS = _normalize_bybit_topic_intervals(BYBIT_KLINE_TOPIC_INTERVALS)
DEFAULT_KLINE_INTERVAL = KLINE_INTERVALS[0] if KLINE_INTERVALS else "1m"


def _current_ms() -> int:
    return int(time.time() * 1000)


def _parse_updated_at_ms(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(_current_ms())


def _normalize_percent_to_ratio(value: Any) -> str:
    try:
        return str(float(value) / 100)
    except (TypeError, ValueError):
        return "0"


def _normalize_trade_side(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"buy", "b"}:
        return "buy"
    if normalized in {"sell", "s"}:
        return "sell"
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _normalize_orderbook_levels(raw_levels: Any, *, reverse_sort: bool, limit: int) -> list[list[str]]:
    if not isinstance(raw_levels, list):
        return []

    levels: list[tuple[float, str, str]] = []
    for item in raw_levels:
        if not isinstance(item, list) or len(item) < 2:
            continue
        price_raw, size_raw = item[0], item[1]
        try:
            price = float(price_raw)
            size = float(size_raw)
        except (TypeError, ValueError):
            continue
        if price <= 0 or size < 0:
            continue
        levels.append((price, str(price_raw), str(size_raw)))

    levels.sort(key=lambda value: value[0], reverse=reverse_sort)
    sliced = levels[: max(limit, 1)]
    return [[price_text, size_text] for _, price_text, size_text in sliced]


def _payload_data(payload: dict[str, Any]) -> Any:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _payload_data_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _parse_bybit_ticker_message(payload: dict[str, Any]) -> dict[str, str] | None:
    topic = payload.get("topic", "")
    if not isinstance(topic, str) or not topic.startswith("tickers."):
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    symbol = topic.split(".", maxsplit=1)[1]
    last_price = data.get("lastPrice")

    if last_price is None:
        return None

    return {
        "symbol": symbol,
        "price": str(last_price),
        "change24h": str(data.get("price24hPcnt", "0")),
        "volume24h": str(data.get("volume24h", "0")),
        "source": "bybit",
        "updated_at_ms": _parse_updated_at_ms(data.get("ts", _current_ms())),
    }


def _parse_bybit_trade_message(payload: dict[str, Any]) -> dict[str, str] | None:
    topic = payload.get("topic", "")
    if not isinstance(topic, str) or not topic.startswith("publicTrade."):
        return None

    data_items = _payload_data_items(payload)
    if not data_items:
        return None

    trade = data_items[-1]
    symbol = topic.split(".", maxsplit=1)[1]
    price = trade.get("p")
    size = trade.get("v")
    if price is None or size is None:
        return None

    side = _normalize_trade_side(trade.get("S", trade.get("side")))
    if side is None:
        return None
    return {
        "symbol": symbol,
        "price": str(price),
        "size": str(size),
        "side": side,
        "source": "bybit",
        "updated_at_ms": _parse_updated_at_ms(trade.get("T", _current_ms())),
    }


def _parse_bybit_orderbook_message(payload: dict[str, Any]) -> dict[str, str] | None:
    topic = payload.get("topic", "")
    if not isinstance(topic, str) or not topic.startswith("orderbook."):
        return None
    topic_parts = topic.split(".")
    if len(topic_parts) != 3:
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    symbol = topic_parts[2]
    bids = _normalize_orderbook_levels(data.get("b"), reverse_sort=True, limit=ORDERBOOK_LEVELS)
    asks = _normalize_orderbook_levels(data.get("a"), reverse_sort=False, limit=ORDERBOOK_LEVELS)
    if not bids and not asks:
        return None

    return {
        "symbol": symbol,
        "source": "bybit",
        "bids_json": json.dumps(bids),
        "asks_json": json.dumps(asks),
        "updated_at_ms": _parse_updated_at_ms(payload.get("ts", data.get("ts", _current_ms()))),
    }


def _parse_bybit_kline_message(payload: dict[str, Any]) -> dict[str, str] | None:
    topic = payload.get("topic", "")
    if not isinstance(topic, str) or not topic.startswith("kline."):
        return None

    topic_parts = topic.split(".")
    if len(topic_parts) != 3:
        return None

    bybit_interval = topic_parts[1]
    interval = BYBIT_TO_CANONICAL_INTERVAL.get(bybit_interval)
    if interval is None:
        return None
    symbol = topic_parts[2]

    data_items = _payload_data_items(payload)
    if not data_items:
        return None

    candle = data_items[-1]
    open_price = candle.get("open", candle.get("o"))
    high_price = candle.get("high", candle.get("h"))
    low_price = candle.get("low", candle.get("l"))
    close_price = candle.get("close", candle.get("c"))
    volume = candle.get("volume", candle.get("v"))
    if any(value is None for value in (open_price, high_price, low_price, close_price, volume)):
        return None

    return {
        "symbol": symbol,
        "interval": interval,
        "open": str(open_price),
        "high": str(high_price),
        "low": str(low_price),
        "close": str(close_price),
        "volume": str(volume),
        "source": "bybit",
        "open_time_ms": _parse_updated_at_ms(
            candle.get("start", candle.get("startTime", candle.get("timestamp", candle.get("end", _current_ms()))))
        ),
        "updated_at_ms": _parse_updated_at_ms(candle.get("end", candle.get("timestamp", _current_ms()))),
    }


def _parse_binance_ticker_message(payload: dict[str, Any]) -> dict[str, str] | None:
    data = _payload_data(payload)
    if not isinstance(data, dict):
        return None

    symbol = data.get("s")
    last_price = data.get("c")
    if not isinstance(symbol, str) or last_price is None:
        return None

    return {
        "symbol": symbol.upper(),
        "price": str(last_price),
        "change24h": _normalize_percent_to_ratio(data.get("P", "0")),
        "volume24h": str(data.get("v", "0")),
        "source": "binance",
        "updated_at_ms": _parse_updated_at_ms(data.get("E", _current_ms())),
    }


def _parse_binance_trade_message(payload: dict[str, Any]) -> dict[str, str] | None:
    data = _payload_data(payload)
    if not isinstance(data, dict):
        return None

    symbol = data.get("s")
    price = data.get("p")
    size = data.get("q")
    if not isinstance(symbol, str) or price is None or size is None:
        return None

    maker_flag = _coerce_bool(data.get("m"))
    if maker_flag is None:
        return None

    side = "sell" if maker_flag else "buy"

    return {
        "symbol": symbol.upper(),
        "price": str(price),
        "size": str(size),
        "side": side,
        "source": "binance",
        "updated_at_ms": _parse_updated_at_ms(data.get("T", data.get("E", _current_ms()))),
    }


def _parse_binance_orderbook_message(payload: dict[str, Any]) -> dict[str, str] | None:
    data = _payload_data(payload)
    if not isinstance(data, dict):
        return None

    symbol = data.get("s")
    if not isinstance(symbol, str):
        stream = payload.get("stream")
        if isinstance(stream, str):
            symbol = stream.split("@", maxsplit=1)[0].upper()
    if not isinstance(symbol, str):
        return None

    bids = _normalize_orderbook_levels(data.get("bids", data.get("b")), reverse_sort=True, limit=ORDERBOOK_LEVELS)
    asks = _normalize_orderbook_levels(data.get("asks", data.get("a")), reverse_sort=False, limit=ORDERBOOK_LEVELS)
    if not bids and not asks:
        return None

    return {
        "symbol": symbol.upper(),
        "source": "binance",
        "bids_json": json.dumps(bids),
        "asks_json": json.dumps(asks),
        "updated_at_ms": _parse_updated_at_ms(data.get("E", data.get("T", _current_ms()))),
    }


def _parse_binance_kline_message(payload: dict[str, Any]) -> dict[str, str] | None:
    data = _payload_data(payload)
    if not isinstance(data, dict):
        return None

    kline = data.get("k")
    if not isinstance(kline, dict):
        return None

    symbol = data.get("s")
    open_price = kline.get("o")
    high_price = kline.get("h")
    low_price = kline.get("l")
    close_price = kline.get("c")
    volume = kline.get("v")
    interval = kline.get("i", DEFAULT_KLINE_INTERVAL)
    if not isinstance(symbol, str) or any(value is None for value in (open_price, high_price, low_price, close_price, volume)):
        return None

    return {
        "symbol": symbol.upper(),
        "interval": str(interval),
        "open": str(open_price),
        "high": str(high_price),
        "low": str(low_price),
        "close": str(close_price),
        "volume": str(volume),
        "source": "binance",
        "open_time_ms": _parse_updated_at_ms(kline.get("t", data.get("E", _current_ms()))),
        "updated_at_ms": _parse_updated_at_ms(kline.get("T", data.get("E", _current_ms()))),
    }


def _ticker_key(ticker: dict[str, str]) -> str:
    return f"{TICKER_KEY_PREFIX}:{ticker['source']}:{ticker['symbol']}"


def _trade_key(trade: dict[str, str]) -> str:
    return f"{TRADE_KEY_PREFIX}:{trade['source']}:{trade['symbol']}"


def _orderbook_key(orderbook: dict[str, str]) -> str:
    return f"{ORDERBOOK_KEY_PREFIX}:{orderbook['source']}:{orderbook['symbol']}"


def _kline_key(kline: dict[str, str]) -> str:
    return f"{KLINE_KEY_PREFIX}:{kline['source']}:{kline['symbol']}:{kline['interval']}"


def _kline_history_key(kline: dict[str, str]) -> str:
    return f"{KLINE_HISTORY_KEY_PREFIX}:{kline['source']}:{kline['symbol']}:{kline['interval']}"


async def _publish_event(
    redis_client: redis.Redis,
    *,
    channel: str,
    key: str,
    payload: dict[str, str],
) -> None:
    await redis_client.hset(key, mapping=payload)
    await redis_client.publish(channel, json.dumps(payload))
    source = payload.get("source", "unknown")
    symbol = payload.get("symbol", "unknown")
    INGESTER_PUBLISHED_EVENTS_TOTAL.labels(channel=channel, source=source, symbol=symbol).inc()


async def _publish_ticker(redis_client: redis.Redis, ticker: dict[str, str]) -> None:
    await _publish_event(redis_client, channel=TICKER_CHANNEL, key=_ticker_key(ticker), payload=ticker)


async def _publish_trade(redis_client: redis.Redis, trade: dict[str, str]) -> None:
    await _publish_event(redis_client, channel=TRADE_CHANNEL, key=_trade_key(trade), payload=trade)


async def _publish_orderbook(redis_client: redis.Redis, orderbook: dict[str, str]) -> None:
    await _publish_event(redis_client, channel=ORDERBOOK_CHANNEL, key=_orderbook_key(orderbook), payload=orderbook)


async def _publish_kline(redis_client: redis.Redis, kline: dict[str, str]) -> None:
    await _publish_event(redis_client, channel=KLINE_CHANNEL, key=_kline_key(kline), payload=kline)
    history_key = _kline_history_key(kline)
    payload_json = json.dumps(kline)
    latest_raw = await redis_client.lindex(history_key, 0)
    if latest_raw:
        try:
            latest_payload = json.loads(latest_raw)
        except json.JSONDecodeError:
            latest_payload = None

        if isinstance(latest_payload, dict):
            latest_open_time = latest_payload.get("open_time_ms")
            current_open_time = kline.get("open_time_ms")
            if latest_open_time is not None and current_open_time is not None and str(latest_open_time) == str(current_open_time):
                await redis_client.lset(history_key, 0, payload_json)
                return

    await redis_client.lpush(history_key, payload_json)
    await redis_client.ltrim(history_key, 0, max(KLINE_HISTORY_LIMIT - 1, 0))


def _sort_klines_by_open_time(klines: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(klines, key=lambda item: int(item.get("open_time_ms", "0")))


async def _fetch_bybit_kline_history(client: httpx.AsyncClient, symbol: str, interval: str) -> list[dict[str, str]]:
    bybit_interval = CANONICAL_TO_BYBIT_INTERVAL.get(interval)
    if bybit_interval is None:
        return []

    try:
        response = await client.get(
            f"{BYBIT_HTTP_URL}/v5/market/kline",
            params={
                "category": "spot",
                "symbol": symbol,
                "interval": bybit_interval,
                "limit": str(KLINE_HISTORY_LIMIT),
            },
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("result", {}).get("list", [])
        if not isinstance(data, list):
            return []

        klines: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, list) or len(item) < 6:
                continue
            open_time_ms, open_price, high_price, low_price, close_price, volume = item[:6]
            kline = {
                "symbol": symbol,
                "interval": interval,
                "open": str(open_price),
                "high": str(high_price),
                "low": str(low_price),
                "close": str(close_price),
                "volume": str(volume),
                "source": "bybit",
                "open_time_ms": _parse_updated_at_ms(open_time_ms),
                "updated_at_ms": _parse_updated_at_ms(open_time_ms),
            }
            klines.append(kline)

        return _sort_klines_by_open_time(klines)
    except Exception as exc:
        LOGGER.warning("Bybit history fetch failed for %s %s: %s", symbol, interval, exc)
        return []


async def _fetch_binance_kline_history(client: httpx.AsyncClient, symbol: str, interval: str) -> list[dict[str, str]]:
    try:
        response = await client.get(
            f"{BINANCE_HTTP_URL}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": str(KLINE_HISTORY_LIMIT),
            },
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return []

        klines: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, list) or len(item) < 7:
                continue
            open_time_ms, open_price, high_price, low_price, close_price, volume, close_time_ms = item[:7]
            kline = {
                "symbol": symbol,
                "interval": interval,
                "open": str(open_price),
                "high": str(high_price),
                "low": str(low_price),
                "close": str(close_price),
                "volume": str(volume),
                "source": "binance",
                "open_time_ms": _parse_updated_at_ms(open_time_ms),
                "updated_at_ms": _parse_updated_at_ms(close_time_ms),
            }
            klines.append(kline)

        return _sort_klines_by_open_time(klines)
    except Exception as exc:
        LOGGER.warning("Binance history fetch failed for %s %s: %s", symbol, interval, exc)
        return []


async def _fetch_bybit_orderbook_snapshot(client: httpx.AsyncClient, symbol: str) -> dict[str, str] | None:
    try:
        response = await client.get(
            f"{BYBIT_HTTP_URL}/v5/market/orderbook",
            params={
                "category": "spot",
                "symbol": symbol,
                "limit": str(max(ORDERBOOK_LEVELS, 1)),
            },
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result", {})
        if not isinstance(result, dict):
            return None

        bids = _normalize_orderbook_levels(result.get("b"), reverse_sort=True, limit=ORDERBOOK_LEVELS)
        asks = _normalize_orderbook_levels(result.get("a"), reverse_sort=False, limit=ORDERBOOK_LEVELS)
        if not bids and not asks:
            return None

        return {
            "symbol": symbol,
            "source": "bybit",
            "bids_json": json.dumps(bids),
            "asks_json": json.dumps(asks),
            "updated_at_ms": _parse_updated_at_ms(result.get("ts", payload.get("time", _current_ms()))),
        }
    except Exception as exc:
        LOGGER.warning("Bybit orderbook fetch failed for %s: %s", symbol, exc)
        return None


async def _warmup_orderbooks(redis_client: redis.Redis) -> None:
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if ENABLE_BYBIT:
            for symbol in SYMBOLS:
                orderbook = await _fetch_bybit_orderbook_snapshot(client, symbol)
                if orderbook is not None:
                    await _publish_orderbook(redis_client, orderbook)


async def _seed_kline_history(redis_client: redis.Redis, klines: list[dict[str, str]]) -> None:
    if not klines:
        return

    latest = klines[-1]
    history_key = _kline_history_key(latest)
    latest_key = _kline_key(latest)

    pipeline = redis_client.pipeline()
    pipeline.delete(history_key)
    for kline in klines:
        pipeline.lpush(history_key, json.dumps(kline))
    pipeline.ltrim(history_key, 0, max(KLINE_HISTORY_LIMIT - 1, 0))
    pipeline.hset(latest_key, mapping=latest)
    await pipeline.execute()


async def _warmup_history(redis_client: redis.Redis) -> None:
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for symbol in SYMBOLS:
            for interval in KLINE_INTERVALS:
                if ENABLE_BYBIT:
                    bybit_history = await _fetch_bybit_kline_history(client, symbol, interval)
                    await _seed_kline_history(redis_client, bybit_history)
                if ENABLE_BINANCE:
                    binance_history = await _fetch_binance_kline_history(client, symbol, interval)
                    await _seed_kline_history(redis_client, binance_history)


def _build_binance_stream_url() -> str:
    streams: list[str] = []
    for symbol in SYMBOLS:
        symbol_lower = symbol.lower()
        streams.append(f"{symbol_lower}@ticker")
        streams.append(f"{symbol_lower}@trade")
        streams.append(f"{symbol_lower}@depth{BINANCE_ORDERBOOK_STREAM_LEVELS}@1000ms")
        for interval in KLINE_INTERVALS:
            streams.append(f"{symbol_lower}@kline_{interval}")
    separator = "&" if "?" in BINANCE_WS_URL else "?"
    return f"{BINANCE_WS_URL}{separator}streams={'/'.join(streams)}"


async def _run_bybit(redis_client: redis.Redis) -> None:
    subscribe_args: list[str] = []
    for symbol in SYMBOLS:
        subscribe_args.append(f"tickers.{symbol}")
        subscribe_args.append(f"publicTrade.{symbol}")
        subscribe_args.append(f"orderbook.{BYBIT_ORDERBOOK_TOPIC_DEPTH}.{symbol}")
        for bybit_interval in BYBIT_KLINE_TOPIC_INTERVALS:
            subscribe_args.append(f"kline.{bybit_interval}.{symbol}")

    subscribe_message = {"op": "subscribe", "args": subscribe_args}

    while True:
        try:
            LOGGER.info("Connecting to Bybit WS %s for symbols: %s", BYBIT_WS_URL, ",".join(SYMBOLS))
            INGESTER_ACTIVE_STREAMS.labels(source="bybit").inc()
            async with connect(BYBIT_WS_URL) as websocket:
                await websocket.send(json.dumps(subscribe_message))
                LOGGER.info("Bybit subscribed: %s", subscribe_message["args"])

                async for raw_message in websocket:
                    try:
                        payload = json.loads(raw_message)
                    except json.JSONDecodeError:
                        LOGGER.warning("Failed to decode Bybit payload: %s", raw_message)
                        continue

                    ticker = _parse_bybit_ticker_message(payload)
                    if ticker is not None:
                        await _publish_ticker(redis_client, ticker)

                    trade = _parse_bybit_trade_message(payload)
                    if trade is not None:
                        await _publish_trade(redis_client, trade)

                    orderbook = _parse_bybit_orderbook_message(payload)
                    if orderbook is not None:
                        await _publish_orderbook(redis_client, orderbook)

                    kline = _parse_bybit_kline_message(payload)
                    if kline is not None:
                        await _publish_kline(redis_client, kline)
        except asyncio.CancelledError:
            raise
        except (ConnectionClosed, WebSocketException, OSError, asyncio.TimeoutError, RedisError) as exc:
            INGESTER_WS_RECONNECTS_TOTAL.labels(source="bybit").inc()
            LOGGER.warning("Bybit stream issue (%s), reconnecting in %.1f seconds", exc, RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
        except Exception:
            INGESTER_WS_RECONNECTS_TOTAL.labels(source="bybit").inc()
            LOGGER.exception("Unexpected Bybit ingester failure, reconnecting in %.1f seconds", RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
        finally:
            INGESTER_ACTIVE_STREAMS.labels(source="bybit").set(0)


async def _run_binance(redis_client: redis.Redis) -> None:
    stream_url = _build_binance_stream_url()

    while True:
        try:
            LOGGER.info("Connecting to Binance WS %s", stream_url)
            INGESTER_ACTIVE_STREAMS.labels(source="binance").inc()
            async with connect(stream_url) as websocket:
                LOGGER.info("Binance subscribed to symbols: %s", ",".join(SYMBOLS))

                async for raw_message in websocket:
                    try:
                        payload = json.loads(raw_message)
                    except json.JSONDecodeError:
                        LOGGER.warning("Failed to decode Binance payload: %s", raw_message)
                        continue

                    ticker = _parse_binance_ticker_message(payload)
                    if ticker is not None:
                        await _publish_ticker(redis_client, ticker)

                    trade = _parse_binance_trade_message(payload)
                    if trade is not None:
                        await _publish_trade(redis_client, trade)

                    orderbook = _parse_binance_orderbook_message(payload)
                    if orderbook is not None:
                        await _publish_orderbook(redis_client, orderbook)

                    kline = _parse_binance_kline_message(payload)
                    if kline is not None:
                        await _publish_kline(redis_client, kline)
        except asyncio.CancelledError:
            raise
        except (ConnectionClosed, WebSocketException, OSError, asyncio.TimeoutError, RedisError) as exc:
            INGESTER_WS_RECONNECTS_TOTAL.labels(source="binance").inc()
            LOGGER.warning("Binance stream issue (%s), reconnecting in %.1f seconds", exc, RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
        except Exception:
            INGESTER_WS_RECONNECTS_TOTAL.labels(source="binance").inc()
            LOGGER.exception("Unexpected Binance ingester failure, reconnecting in %.1f seconds", RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
        finally:
            INGESTER_ACTIVE_STREAMS.labels(source="binance").set(0)


async def _run_bybit_orderbook_http_fallback(redis_client: redis.Redis) -> None:
    if BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS <= 0:
        return

    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            try:
                for symbol in SYMBOLS:
                    orderbook = await _fetch_bybit_orderbook_snapshot(client, symbol)
                    if orderbook is not None:
                        await _publish_orderbook(redis_client, orderbook)
                await asyncio.sleep(BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "Bybit orderbook HTTP fallback failed, retrying in %.1f seconds",
                    BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS,
                )
                await asyncio.sleep(BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS)


async def run() -> None:
    if not SYMBOLS:
        raise ValueError("SYMBOLS must contain at least one instrument")
    if ORDERBOOK_LEVELS < 1:
        raise ValueError("ORDERBOOK_LEVELS must be >= 1")
    if BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS < 0:
        raise ValueError("BYBIT_ORDERBOOK_HTTP_FALLBACK_SECONDS must be >= 0")
    if not KLINE_INTERVALS:
        raise ValueError("KLINE_INTERVALS must contain supported values (1m,5m,15m,1h)")
    if ENABLE_BYBIT and not BYBIT_KLINE_TOPIC_INTERVALS:
        raise ValueError("BYBIT_KLINE_TOPIC_INTERVALS must contain supported values (1,5,15,60)")
    if not ENABLE_BYBIT and not ENABLE_BINANCE:
        raise ValueError("At least one source must be enabled (ENABLE_BYBIT or ENABLE_BINANCE)")
    if INGESTER_METRICS_PORT < 1:
        raise ValueError("INGESTER_METRICS_PORT must be >= 1")

    start_http_server(INGESTER_METRICS_PORT)
    LOGGER.info("Prometheus metrics exporter started on :%s", INGESTER_METRICS_PORT)
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    tasks: list[asyncio.Task[None]] = []

    history_warmup_started = perf_counter()
    await _warmup_history(redis_client)
    INGESTER_WARMUP_DURATION_SECONDS.labels(stage="history").observe(perf_counter() - history_warmup_started)

    orderbook_warmup_started = perf_counter()
    await _warmup_orderbooks(redis_client)
    INGESTER_WARMUP_DURATION_SECONDS.labels(stage="orderbook").observe(perf_counter() - orderbook_warmup_started)

    if ENABLE_BYBIT:
        tasks.append(asyncio.create_task(_run_bybit(redis_client), name="ingester-bybit"))
        tasks.append(asyncio.create_task(_run_bybit_orderbook_http_fallback(redis_client), name="ingester-bybit-orderbook-http"))
    if ENABLE_BINANCE:
        tasks.append(asyncio.create_task(_run_binance(redis_client), name="ingester-binance"))

    enabled_sources = [task.get_name().replace("ingester-", "") for task in tasks]
    LOGGER.info("Market ingester started with sources: %s", ",".join(enabled_sources))

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await redis_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())
