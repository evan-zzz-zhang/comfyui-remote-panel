from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from aiohttp import web

from .app import create_app
from .autostart import (
    AutostartError,
    install_autostart,
    remove_autostart,
    status_autostart,
)
from .config import ConfigError, load_config
from .doctor import run_doctor
from .panel_control import PanelControlError, PanelController
from .setup_wizard import SetupError, run_setup


def configure_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    rotating = RotatingFileHandler(
        data_dir / "panel.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    rotating.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[stream, rotating], force=True)


def _add_config_argument(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
    kwargs = {"help": "Path to config.toml"}
    if suppress_default:
        kwargs["default"] = argparse.SUPPRESS
    else:
        kwargs["default"] = "config.toml"
    parser.add_argument("--config", **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comfyui-remote-panel",
        description="Comfy Remote — mobile-first remote control for local ComfyUI workflows.",
    )
    _add_config_argument(parser)
    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser("setup", help="Run the first-time configuration wizard")
    _add_config_argument(setup_parser, suppress_default=True)

    for command, help_text in (
        ("start", "Start the panel in the background"),
        ("stop", "Stop the panel started by Comfy Remote"),
        ("restart", "Restart the panel"),
        ("status", "Show panel process status"),
    ):
        child = subparsers.add_parser(command, help=help_text)
        _add_config_argument(child, suppress_default=True)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose the current installation")
    _add_config_argument(doctor_parser, suppress_default=True)
    doctor_parser.add_argument(
        "--report",
        action="store_true",
        help="Emit a sanitized Markdown report suitable for a GitHub issue",
    )

    autostart_parser = subparsers.add_parser("autostart", help="Manage Windows login autostart")
    _add_config_argument(autostart_parser, suppress_default=True)
    autostart_subparsers = autostart_parser.add_subparsers(dest="autostart_command", required=True)
    for command, help_text in (
        ("install", "Install the Windows scheduled task"),
        ("status", "Show scheduled-task status"),
        ("remove", "Remove the Windows scheduled task"),
    ):
        child = autostart_subparsers.add_parser(command, help=help_text)
        _add_config_argument(child, suppress_default=True)

    return parser


def _foreground(config_path: str) -> int:
    config = load_config(config_path)
    configure_logging(config.data_dir)
    web.run_app(
        create_app(config),
        host=config.host,
        port=config.port,
        access_log=None,
    )
    return 0


def _print_status(controller: PanelController) -> None:
    status = controller.status()
    print(f"Panel      {'Running' if status.running else 'Stopped'}")
    print(f"PID        {status.pid if status.pid is not None else '—'}")
    print(f"Port       {status.port}")
    print(f"Health     {'OK' if status.health_ok else '—'}")
    if status.reason and not status.running:
        print(f"State      {status.reason}")


def _run_command(args: argparse.Namespace) -> int:
    config_path = args.config
    if args.command is None:
        return _foreground(config_path)

    if args.command == "setup":
        return run_setup(config_path)

    if args.command == "doctor":
        exit_code, output = run_doctor(config_path, report=args.report)
        print(output)
        return exit_code

    if args.command in {"start", "stop", "restart", "status"}:
        controller = PanelController(config_path)
        if args.command == "start":
            before = controller.status()
            status = controller.start()
            if before.running:
                print("Comfy Remote 已运行")
            else:
                print("Comfy Remote 已启动")
            _print_status(controller)
            return 0 if status.health_ok else 1
        if args.command == "stop":
            before = controller.status()
            controller.stop()
            print("Comfy Remote 已停止" if before.running else "Comfy Remote 未运行")
            return 0
        if args.command == "restart":
            controller.restart()
            print("Comfy Remote 已重启")
            _print_status(controller)
            return 0
        _print_status(controller)
        status = controller.status()
        if status.reason == "port-occupied":
            return 1
        return 0

    if args.command == "autostart":
        if args.autostart_command == "install":
            result = install_autostart(config_path)
            print(result.output or "Autostart installed")
            return 0
        if args.autostart_command == "status":
            result = status_autostart(config_path)
            print(result.output or "not-registered")
            return 0
        result = remove_autostart(config_path)
        print(result.output or "Autostart removed")
        return 0

    raise RuntimeError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run_command(args)
    except (ConfigError, PanelControlError, AutostartError, SetupError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
