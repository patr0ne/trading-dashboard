# trading-dashboard

MVP real-time crypto market dashboard.

## Screenshots

<p align="center">
  <a href="https://gifyu.com/image/bqaCi">
    <img src="https://s13.gifyu.com/images/bqaCi.gif" alt="" width="920" />
  </a>
</p>

| | |
|---|---|
| <a href="https://gifyu.com/image/bqaCg"><img src="https://s13.gifyu.com/images/bqaCg.png" alt="" width="100%" /></a> | <a href="https://gifyu.com/image/bqaCc"><img src="https://s13.gifyu.com/images/bqaCc.png" alt="" width="100%" /></a> |

## Planned modules

- `ingester` (Python): exchange websocket ingestion and normalization
- `api_server` (FastAPI): REST + WebSocket gateway
- `frontend` (Next.js): live charts and tables
- `infra`: monitoring and deployment config

MVP phase 1 (`ticker/trade/kline` flow) is implemented:
- `ingester` reads Bybit + Binance market streams and writes to Redis
- `api_server` exposes snapshot REST and realtime websocket for tickers/trades/klines
- `frontend` displays live cards and kline chart via App Router.

## Quick start (MVP market streams)

1. Create local env file:
   - copy `.env.example` -> `.env`
   - optional: change external ports in `.env` (`FRONTEND_PORT`, `API_PUBLIC_PORT`, `GRAFANA_PORT`, `PROMETHEUS_PORT`, `REDIS_PUBLIC_PORT`)
   - optional: change Grafana admin credentials in `.env` (`GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`)
2. Start local stack:
   - `make up`
3. (Optional) Start production-oriented stack:
   - `make up-prod`
3. Open:
   - frontend: `http://localhost:3110`
   - grafana: `http://localhost:3001` (admin/admin)
   - prometheus: `http://localhost:9090`
   - api health: `http://localhost:8000/health`
   - api metrics: `http://localhost:8000/metrics`
   - tickers snapshot: `http://localhost:8000/api/tickers`
   - trades snapshot: `http://localhost:8000/api/trades`
   - klines snapshot: `http://localhost:8000/api/klines`
   - kline history: `http://localhost:8000/api/klines/history?source=binance&symbol=BTCUSDT&interval=1m&limit=120`

## Local environments (separate per repo)

For this repository, use a dedicated local environment inside `trading-dashboard/`.

Python services (`ingester`, `api_server`):

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -U pip
```

Frontend (`frontend`):

```bash
cd frontend
npm install
```

Recommended: keep this environment isolated and do not reuse it across other portfolio repos.

## Common commands

```bash
make init
make up
make up-prod
make down
make down-prod
```

The default `docker-compose.yml` uses local images (`Dockerfile.local`).
Production-oriented build overrides are in `docker-compose.prod.yml` (`Dockerfile.prod`).

Default external ports:
- frontend: `FRONTEND_PORT=3110`
- api: `API_PUBLIC_PORT=8000`
- grafana: `GRAFANA_PORT=3001`
- prometheus: `PROMETHEUS_PORT=9090`
- redis: `REDIS_PUBLIC_PORT=6390`

Default Grafana credentials:
- user: `GRAFANA_ADMIN_USER=admin`
- password: `GRAFANA_ADMIN_PASSWORD=admin`

## Quality Gates

- Lint gate (frontend): `cd frontend && npm run lint`
- Test gate (frontend): `cd frontend && npm run test`
- CI gate: `.github/workflows/ci.yml` on `push` and `pull_request`

## Observability

- `api_server` exports Prometheus metrics on `GET /metrics`
- `ingester` exports Prometheus metrics on `:9108/metrics`
- Prometheus scrape config: `infra/prometheus/prometheus.yml`
- Grafana provisioning and ready dashboard:
  - datasource: `infra/grafana/provisioning/datasources/prometheus.yml`
  - dashboard provider: `infra/grafana/provisioning/dashboards/dashboards.yml`
  - dashboard JSON: `infra/grafana/dashboards/trading-observability.json`

## Validation status

- Verified locally via Docker Compose:
  - Prometheus readiness: `GET http://localhost:9090/-/ready` -> `200`
  - Prometheus active targets: `api_server` and `ingester` are `up`
  - Grafana health: `GET http://localhost:3001/api/health` -> `200`
  - Grafana provisioning: Prometheus datasource and dashboard are available

## License

This project is licensed under the MIT License. See `LICENSE`.

## Market data usage notice

This project consumes public market data from Binance and Bybit APIs.
Before running a public deployment, verify the current exchange Terms of Service and market-data redistribution policies for your specific use case/jurisdiction.
