# infra

Infrastructure and observability configs for local/demo runtime.

## Contents

- `prometheus/prometheus.yml` - scrape jobs for `api_server` and `ingester`
- `grafana/provisioning/datasources/prometheus.yml` - provisioned Prometheus datasource
- `grafana/provisioning/dashboards/dashboards.yml` - dashboard provider config
- `grafana/dashboards/trading-observability.json` - prebuilt dashboard with API and ingester metrics

## Smoke checks

Run stack:
- `docker compose up -d redis ingester api prometheus grafana`

Verify:
- Prometheus ready: `http://localhost:9090/-/ready` (HTTP `200`, default `PROMETHEUS_PORT`)
- Prometheus targets: `http://localhost:9090/api/v1/targets` (`api_server` and `ingester` should be `up`)
- Grafana health: `http://localhost:3001/api/health` (HTTP `200`, default `GRAFANA_PORT`)
