# CloudPulse

A small cloud-native uptime / health monitoring service, written in
**standard-library-only Python** — no third-party dependencies, so it runs
anywhere Python 3.11+ runs.

CloudPulse probes a list of URLs on a schedule and records up/down status,
latency, and history. It exposes Kubernetes-style liveness/readiness probes,
Prometheus metrics, a JSON status API, and a small HTML dashboard.

## What it does

- Checks each configured target every `interval_seconds` (default 30s)
  with a per-request timeout; a target is **up** when the HTTP status
  matches its `expected_status` (default 200).
- Keeps the last N results per target in memory (default 100) and
  computes uptime ratios and check counts.
- Serves:
  - `GET /healthz` — liveness probe, `{"status": "ok"}` while running.
  - `GET /readyz` — readiness probe, 200 once the first check round has
    run, 503 before that.
  - `GET /metrics` — Prometheus exposition format (`cloudpulse_up`,
    `cloudpulse_latency_milliseconds`, `cloudpulse_checks_total`,
    `cloudpulse_uptime_ratio`).
  - `GET /api/status` — JSON snapshot of every target, including history.
  - `GET /` — HTML dashboard.

## Configuration

Edit `config.yaml` (YAML) or use a JSON file with the same shape:

```yaml
interval_seconds: 30
timeout_seconds: 5
host: 0.0.0.0
port: 8080
history_size: 100
targets:
  - name: example
    url: https://example.com
    expected_status: 200
  - name: api-health
    url: https://api.example.com/health
    expected_status: 200
    method: HEAD        # GET or HEAD
    timeout_seconds: 2  # optional per-target override
```

Validation is strict: bad URLs, duplicate names/URLs, non-positive
intervals/timeouts, and out-of-range status codes are rejected at startup
with a clear error instead of silently misbehaving.

## Run it

```bash
python3 -m cloudpulse                 # uses config.yaml
python3 -m cloudpulse --config my.json --port 9090
```

Then open http://localhost:8080/ or scrape http://localhost:8080/metrics.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```

The suite (34 tests) covers the checker (against a local HTTP server —
no internet needed), config parsing/validation for YAML and JSON, the
history store and Prometheus output format, and every HTTP endpoint
including the 503-before-ready behaviour of `/readyz`.

## Deploy with Docker

```bash
docker build -t cloudpulse .
docker run --rm -p 8080:8080 cloudpulse
```

The image is multi-stage (`python:3.12-slim`), runs as a non-root user,
and has a `/healthz` HEALTHCHECK.

## Deploy with kubectl

```bash
kubectl apply -f k8s/
kubectl get pods -l app=cloudpulse
kubectl port-forward svc/cloudpulse 8080:80
```

The Deployment mounts the targets list from a ConfigMap and wires
`/healthz` as the liveness probe and `/readyz` as the readiness probe.
Edit `k8s/configmap.yaml` to change targets, or build/push the image
referenced in `k8s/deployment.yaml` (`ghcr.io/872000/cloudpulse:latest`).

## Deploy with Helm

```bash
helm install cloudpulse ./helm/cloudpulse
# or override targets / replicas:
helm install cloudpulse ./helm/cloudpulse \
  --set replicaCount=2 \
  --set config.intervalSeconds=15
```

Values live in `helm/cloudpulse/values.yaml`; `helm template` renders the
Deployment, Service, and ConfigMap.

## Project layout

```
cloudpulse/          # the service package
  __main__.py        # CLI entry point
  config.py          # YAML/JSON config loading + validation
  checker.py         # one HTTP probe -> CheckResult
  store.py           # thread-safe history + uptime rollups
  metrics.py         # Prometheus exposition rendering
  server.py          # HTTP server, probes, API, dashboard, scheduler
tests/               # unittest suite (stdlib only)
k8s/                 # Deployment + Service + ConfigMap
helm/cloudpulse/     # Helm chart
config.yaml          # default config
Dockerfile           # multi-stage, non-root, HEALTHCHECK
```

## License

MIT — see [LICENSE](LICENSE).
