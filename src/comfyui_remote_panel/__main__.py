from __future__ import annotations

import argparse
import logging

from aiohttp import web

from .app import create_app
from .config import ConfigError, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="ComfyUI Remote Panel")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as exc:
        parser.error(str(exc))
    web.run_app(create_app(config), host=config.host, port=config.port, access_log=None)


if __name__ == "__main__":
    main()

