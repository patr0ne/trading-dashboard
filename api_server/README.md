# api_server

FastAPI gateway for market streams:
- `GET /health` healthcheck
- `GET /api/tickers` current snapshots (`source + symbol`)
- `GET /api/trades` latest trades (`source + symbol`)
- `GET /api/klines` latest klines (`source + symbol + interval`)
- `GET /api/klines/history?source=...&symbol=...&interval=...&limit=...&before_open_time_ms=...` kline history for charts (supports left-scroll pagination; falls back to exchange REST when Redis history is exhausted)
- `WS /ws/tickers` live ticker updates
- `WS /ws/trades` live trade updates
- `WS /ws/klines` live kline updates.
