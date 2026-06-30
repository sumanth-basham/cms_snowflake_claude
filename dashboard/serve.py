from __future__ import annotations

import os
import signal
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard"


def main() -> None:
    api_host = os.getenv("API_HOST", "127.0.0.1")
    api_port = os.getenv("API_PORT", "8000")
    dashboard_host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    dashboard_port = int(os.getenv("DASHBOARD_PORT", "8080"))

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app", "--host", api_host, "--port", api_port],
        cwd=ROOT,
        env=env,
    )

    handler = partial(SimpleHTTPRequestHandler, directory=str(DASHBOARD_DIR))
    server = ThreadingHTTPServer((dashboard_host, dashboard_port), handler)
    print(f"API server:       http://{api_host}:{api_port}")
    print(f"Dashboard server: http://{dashboard_host}:{dashboard_port}")
    print("Press Ctrl+C to stop both services.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if api_process.poll() is None:
            api_process.send_signal(signal.SIGTERM)
            api_process.wait(timeout=10)


if __name__ == "__main__":
    main()
