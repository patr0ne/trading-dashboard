import asyncio
from contextlib import asynccontextmanager
import json
import os
from time import perf_counter
import time
from collections.abc import AsyncIterator
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SYMBOLS = [symbol.strip().upper() for symbol in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if symbol.strip()]
SOURCES = [source.strip().lower() for source in os.getenv("SOURCES", "bybit,binance").split(",") if source.strip()]
TICKER_CHANNEL = os.getenv("TICKER_CHANNEL", "ticker_updates")
TICKER_KEY_PREFIX = os.getenv("TICKER_KEY_PREFIX", "ticker")
TRADE_CHANNEL = os.getenv("TRADE_CHANNEL", "trade_updates")
TRADE_KEY_PREFIX = os.getenv("TRADE_KEY_PREFIX", "trade")
ORDERBOOK_CHANNEL = os.getenv("ORDERBOOK_CHANNEL", "orderbook_updates")
ORDERBOOK_KEY_PREFIX = os.getenv("ORDERBOOK_KEY_PREFIX", "orderbook")
KLINE_CHANNEL = os.getenv("KLINE_CHANNEL", "kline_updates")
KLINE_KEY_PREFIX = os.getenv("KLINE_KEY_PREFIX", "kline")
KLINE_HISTORY_KEY_PREFIX = os.getenv("KLINE_HISTORY_KEY_PREFIX", "kline_history")
KLINE_INTERVALS = [value.strip() for value in os.getenv("KLINE_INTERVALS", "1m,5m,15m,1h").split(",") if value.strip()]
DEFAULT_KLINE_INTERVAL = KLINE_INTERVALS[0] if KLINE_INTERVALS else "1m"
KLINE_HISTORY_DEFAULT_LIMIT = int(os.getenv("KLINE_HISTORY_DEFAULT_LIMIT", "120"))
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
HEARTBEAT_SECONDS = float(os.getenv("WS_HEARTBEAT_SECONDS", "15"))

HTTP_REQUESTS_TOTAL = Counter(
    "trading_api_http_requests_total",
    "Total number of HTTP requests served by api_server",
    ("method", "path", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "trading_api_http_request_duration_seconds",
    "HTTP request latency in seconds for api_server",
    ("method", "path"),
)
WS_CONNECTIONS = Gauge(
    "trading_api_ws_connections",
    "Active websocket connections by stream in api_server",
    ("stream",),
)
WS_MESSAGES_TOTAL = Counter(
    "trading_api_ws_messages_total",
    "Total websocket messages sent by api_server",
    ("stream", "kind"),
)

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    application.state.redis = redis_client
    try:
        yield
    finally:
        await redis_client.aclose()


app = FastAPI(title="Trading Dashboard API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_http_middleware(request, call_next):  # type: ignore[no-untyped-def]
    path = request.url.path
    method = request.method
    start = perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(perf_counter() - start)


def _redis_key(prefix: str, source: str, symbol: str, interval: str | None = None) -> str:
    key_parts = [prefix, source, symbol]
    if interval:
        key_parts.append(interval)
    return ":".join(key_parts)


async def _fetch_snapshot(
    redis_client: redis.Redis,
    *,
    prefix: str,
    source: str,
    symbol: str,
    interval: str | None = None,
) -> dict[str, str] | None:
    value = await redis_client.hgetall(_redis_key(prefix, source, symbol, interval))
    return value or None


async def _fetch_tickers(redis_client: redis.Redis) -> list[dict[str, str]]:
    snapshots = await asyncio.gather(
        *[
            _fetch_snapshot(redis_client, prefix=TICKER_KEY_PREFIX, source=source, symbol=symbol)
            for source in SOURCES
            for symbol in SYMBOLS
        ]
    )
    return [snapshot for snapshot in snapshots if snapshot is not None]


async def _fetch_trades(redis_client: redis.Redis) -> list[dict[str, str]]:
    snapshots = await asyncio.gather(
        *[
            _fetch_snapshot(redis_client, prefix=TRADE_KEY_PREFIX, source=source, symbol=symbol)
            for source in SOURCES
            for symbol in SYMBOLS
        ]
    )
    return [snapshot for snapshot in snapshots if snapshot is not None]


async def _fetch_orderbooks(
    redis_client: redis.Redis,
    *,
    source: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, str]]:
    sources = [source] if source else SOURCES
    symbols = [symbol] if symbol else SYMBOLS
    snapshots = await asyncio.gather(
        *[
            _fetch_snapshot(redis_client, prefix=ORDERBOOK_KEY_PREFIX, source=source_name, symbol=symbol_name)
            for source_name in sources
            for symbol_name in symbols
        ]
    )
    return [snapshot for snapshot in snapshots if snapshot is not None]


async def _fetch_klines(redis_client: redis.Redis, *, interval: str | None = None) -> list[dict[str, str]]:
    intervals = [interval] if interval else KLINE_INTERVALS
    snapshots = await asyncio.gather(
        *[
            _fetch_snapshot(redis_client, prefix=KLINE_KEY_PREFIX, source=source, symbol=symbol, interval=each_interval)
            for source in SOURCES
            for symbol in SYMBOLS
            for each_interval in intervals
        ]
    )
    return [snapshot for snapshot in snapshots if snapshot is not None]


async def _fetch_kline_history(
    redis_client: redis.Redis,
    *,
    source: str,
    symbol: str,
    interval: str,
    limit: int,
) -> list[dict[str, str]]:
    history_key = _redis_key(KLINE_HISTORY_KEY_PREFIX, source, symbol, interval)
    raw_items = await redis_client.lrange(history_key, 0, max((limit * 4) - 1, limit - 1))

    klines: list[dict[str, str]] = []
    seen_open_time: set[int] = set()
    for raw in raw_items:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        open_time_ms = _extract_open_time_ms(payload)
        if open_time_ms in seen_open_time:
            continue
        seen_open_time.add(open_time_ms)

        normalized = {key: str(value) for key, value in payload.items()}
        klines.append(normalized)
        if len(klines) >= limit:
            break

    klines.reverse()
    return klines


def _decode_pubsub_data(data: Any) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return str(data)


def _extract_updated_at_ms(payload: dict[str, Any]) -> int:
    raw = payload.get("updated_at_ms")
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _extract_open_time_ms(payload: dict[str, Any]) -> int:
    raw = payload.get("open_time_ms")
    if raw is None:
        return _extract_updated_at_ms(payload)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _extract_updated_at_ms(payload)


def _ticker_identity(payload: dict[str, Any]) -> str | None:
    symbol = payload.get("symbol")
    source = payload.get("source")
    if not isinstance(symbol, str) or not isinstance(source, str):
        return None
    return f"{source}:{symbol}"


def _kline_identity(payload: dict[str, Any]) -> str | None:
    base = _ticker_identity(payload)
    interval = payload.get("interval")
    if base is None or not isinstance(interval, str):
        return None
    return f"{base}:{interval}"


async def _ws_entity_stream(
    websocket: WebSocket,
    *,
    stream_name: str,
    channel: str,
    fetcher: Callable[[redis.Redis], Awaitable[list[dict[str, str]]]],
    identity_getter: Callable[[dict[str, Any]], str | None],
) -> None:
    await websocket.accept()
    WS_CONNECTIONS.labels(stream=stream_name).inc()
    redis_client: redis.Redis = app.state.redis

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    latest_sent_by_identity: dict[str, int] = {}

    for snapshot in await fetcher(redis_client):
        identity = identity_getter(snapshot)
        if identity:
            latest_sent_by_identity[identity] = _extract_updated_at_ms(snapshot)
        await websocket.send_text(json.dumps(snapshot))
        WS_MESSAGES_TOTAL.labels(stream=stream_name, kind="snapshot").inc()

    last_activity = time.time()

    try:
        while True:
            message: dict[str, Any] | None = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                payload_text = _decode_pubsub_data(message.get("data"))
                try:
                    parsed_payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    await websocket.send_text(payload_text)
                    last_activity = time.time()
                    continue

                if isinstance(parsed_payload, dict):
                    identity = identity_getter(parsed_payload)
                    if identity:
                        updated_at_ms = _extract_updated_at_ms(parsed_payload)
                        if updated_at_ms <= latest_sent_by_identity.get(identity, 0):
                            continue
                        latest_sent_by_identity[identity] = updated_at_ms

                await websocket.send_text(payload_text)
                WS_MESSAGES_TOTAL.labels(stream=stream_name, kind="update").inc()
                last_activity = time.time()
                continue

            if time.time() - last_activity >= HEARTBEAT_SECONDS:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
                WS_MESSAGES_TOTAL.labels(stream=stream_name, kind="heartbeat").inc()
                last_activity = time.time()
    except WebSocketDisconnect:
        pass
    finally:
        WS_CONNECTIONS.labels(stream=stream_name).dec()
        await pubsub.unsubscribe(channel)
        await pubsub.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/tickers")
async def get_tickers() -> list[dict[str, str]]:
    redis_client: redis.Redis = app.state.redis
    return await _fetch_tickers(redis_client)


@app.get("/api/trades")
async def get_trades() -> list[dict[str, str]]:
    redis_client: redis.Redis = app.state.redis
    return await _fetch_trades(redis_client)


@app.get("/api/orderbooks")
async def get_orderbooks(
    source: str | None = Query(default=None, min_length=1),
    symbol: str | None = Query(default=None, min_length=1),
) -> list[dict[str, str]]:
    normalized_source: str | None = None
    normalized_symbol: str | None = None

    if source is not None:
        normalized_source = source.strip().lower()
        if normalized_source not in SOURCES:
            raise HTTPException(status_code=400, detail=f"Unknown source: {normalized_source}")
    if symbol is not None:
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol not in SYMBOLS:
            raise HTTPException(status_code=400, detail=f"Unknown symbol: {normalized_symbol}")

    redis_client: redis.Redis = app.state.redis
    return await _fetch_orderbooks(redis_client, source=normalized_source, symbol=normalized_symbol)


@app.get("/api/klines")
async def get_klines(interval: str | None = Query(default=None, min_length=1)) -> list[dict[str, str]]:
    normalized_interval: str | None = None
    if interval is not None:
        normalized_interval = interval.strip()
        if normalized_interval not in KLINE_INTERVALS:
            raise HTTPException(status_code=400, detail=f"Unknown interval: {normalized_interval}")

    redis_client: redis.Redis = app.state.redis
    return await _fetch_klines(redis_client, interval=normalized_interval)


@app.get("/api/klines/history")
async def get_kline_history(
    source: str = Query(..., min_length=1),
    symbol: str = Query(..., min_length=1),
    interval: str = Query(DEFAULT_KLINE_INTERVAL, min_length=1),
    limit: int = Query(KLINE_HISTORY_DEFAULT_LIMIT, ge=1, le=500),
) -> list[dict[str, str]]:
    normalized_source = source.strip().lower()
    normalized_symbol = symbol.strip().upper()
    normalized_interval = interval.strip()

    if normalized_source not in SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {normalized_source}")
    if normalized_symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {normalized_symbol}")
    if normalized_interval not in KLINE_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unknown interval: {normalized_interval}")

    redis_client: redis.Redis = app.state.redis
    return await _fetch_kline_history(
        redis_client,
        source=normalized_source,
        symbol=normalized_symbol,
        interval=normalized_interval,
        limit=limit,
    )


@app.websocket("/ws/tickers")
async def ws_tickers(websocket: WebSocket) -> None:
    await _ws_entity_stream(
        websocket,
        stream_name="tickers",
        channel=TICKER_CHANNEL,
        fetcher=_fetch_tickers,
        identity_getter=_ticker_identity,
    )


@app.websocket("/ws/trades")
async def ws_trades(websocket: WebSocket) -> None:
    await _ws_entity_stream(
        websocket,
        stream_name="trades",
        channel=TRADE_CHANNEL,
        fetcher=_fetch_trades,
        identity_getter=_ticker_identity,
    )


@app.websocket("/ws/klines")
async def ws_klines(websocket: WebSocket) -> None:
    await _ws_entity_stream(
        websocket,
        stream_name="klines",
        channel=KLINE_CHANNEL,
        fetcher=_fetch_klines,
        identity_getter=_kline_identity,
    )


@app.websocket("/ws/orderbooks")
async def ws_orderbooks(websocket: WebSocket) -> None:
    await _ws_entity_stream(
        websocket,
        stream_name="orderbooks",
        channel=ORDERBOOK_CHANNEL,
        fetcher=_fetch_orderbooks,
        identity_getter=_ticker_identity,
    )
