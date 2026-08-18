"""CGV 예매 오픈 알리미 — 웹 서버 진입점."""
from __future__ import annotations

import logging
import os

import uvicorn

from cgvwatch.web.server import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
