"""CloudPulse entry point: ``python -m cloudpulse [--config ...]``."""

from __future__ import annotations

import argparse
import signal
import threading

from .config import load_config
from .server import create_server, run_scheduler
from .store import HistoryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cloudpulse", description="Cloud-native uptime monitor."
    )
    parser.add_argument("--config", default="config.yaml",
                        help="path to config file (default: config.yaml)")
    parser.add_argument("--host", default=None, help="override config host")
    parser.add_argument("--port", type=int, default=None,
                        help="override config port")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port

    store = HistoryStore(history_size=config.history_size)
    ready_event = threading.Event()
    stop_event = threading.Event()

    scheduler = threading.Thread(
        target=run_scheduler,
        args=(config, store, ready_event, stop_event),
        name="cloudpulse-scheduler",
        daemon=True,
    )
    scheduler.start()

    server = create_server(config, store, ready_event)
    print(
        f"CloudPulse listening on http://{config.host}:{config.port} "
        f"monitoring {len(config.targets)} target(s)",
        flush=True,
    )

    def _shutdown(signum, _frame):
        # Only set the event here: calling server.shutdown() from inside
        # a signal handler would deadlock (it waits for serve_forever,
        # which is running on this same thread).
        print("Shutting down...", flush=True)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    server_thread = threading.Thread(
        target=server.serve_forever, name="cloudpulse-http", daemon=True
    )
    server_thread.start()
    stop_event.wait()  # blocked until SIGINT/SIGTERM
    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
