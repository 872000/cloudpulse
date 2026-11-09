# syntax=docker/dockerfile:1
# CloudPulse — multi-stage build. The runtime image is plain
# python:3.12-slim with no extra packages: the service is stdlib-only.
FROM python:3.12-slim AS builder
WORKDIR /app
COPY cloudpulse/ ./cloudpulse/
COPY config.yaml ./
RUN python3 -m compileall cloudpulse

FROM python:3.12-slim AS runtime
WORKDIR /app
# Run as a non-root user.
RUN groupadd -r cloudpulse && useradd -r -g cloudpulse cloudpulse
COPY --from=builder /app/cloudpulse ./cloudpulse
COPY --from=builder /app/config.yaml ./config.yaml
USER cloudpulse
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
CMD ["python3", "-m", "cloudpulse"]
