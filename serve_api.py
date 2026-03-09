from __future__ import annotations

import argparse

from fed_tracker.http_api import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Fed textual analysis HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
