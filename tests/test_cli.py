from comfyui_remote_panel.cli import build_parser


def test_cli_keeps_legacy_foreground_mode():
    args = build_parser().parse_args(["--config", "legacy.toml"])
    assert args.command is None
    assert args.config == "legacy.toml"
    assert args.lang == "auto"


def test_cli_accepts_public_commands_and_config_after_subcommand():
    parser = build_parser()
    setup = parser.parse_args(["setup", "--config", "one.toml", "--lang", "en"])
    assert setup.config == "one.toml"
    assert setup.lang == "en"
    assert parser.parse_args(["start"]).command == "start"
    assert parser.parse_args(["stop"]).command == "stop"
    assert parser.parse_args(["restart"]).command == "restart"
    assert parser.parse_args(["status"]).command == "status"

    doctor = parser.parse_args(["doctor", "--report", "--config", "doctor.toml", "--lang", "zh-CN"])
    assert doctor.command == "doctor"
    assert doctor.report is True
    assert doctor.config == "doctor.toml"
    assert doctor.lang == "zh-CN"

    autostart = parser.parse_args(["autostart", "install", "--config", "auto.toml", "--lang", "en"])
    assert autostart.command == "autostart"
    assert autostart.autostart_command == "install"
    assert autostart.config == "auto.toml"
    assert autostart.lang == "en"
