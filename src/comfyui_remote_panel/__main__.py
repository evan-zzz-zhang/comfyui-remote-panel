from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler

from aiohttp import web

from .app import create_app
from .config import ConfigError, load_config


def configure_logging(data_dir) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    rotating = RotatingFileHandler(
        data_dir / "panel.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    rotating.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[stream, rotating], force=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="ComfyUI Remote Panel")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as exc:
        parser.error(str(exc))
    configure_logging(config.data_dir)
    web.run_app(create_app(config), host=config.host, port=config.port, access_log=None)


if __name__ == "__main__":
    main()
