from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable
from urllib.request import urlopen

from .autostart import AutostartError, install_autostart, status_autostart
from .config import Config, ConfigError, load_config
from .launch_discovery import discover_portable_start_options
from .tailscale import TailscaleError, enable_serve, inspect_tailscale


class SetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComfyInstallation:
    root: Path
    comfy_root: Path
    input_dir: Path
    output_dir: Path
    python_executable: Path | None
    start_command: tuple[str, ...]
    portable: bool


def inspect_comfyui_root(value: str | Path) -> ComfyInstallation | None:
    root = Path(value).expanduser().resolve()

    # Accept both the portable bundle root and its nested ComfyUI directory.
    if (
        (root / "main.py").is_file()
        and (root.parent / "python_embeded" / "python.exe").is_file()
        and root.name.lower() == "comfyui"
    ):
        root = root.parent

    portable_main = root / "ComfyUI" / "main.py"
    standard_main = root / "main.py"
    if portable_main.is_file():
        comfy_root = root / "ComfyUI"
        embedded = root / "python_embeded" / "python.exe"
        python_executable = embedded if embedded.is_file() else None
        command: tuple[str, ...] = (
            str(python_executable) if python_executable else sys.executable,
            "-s",
            "ComfyUI/main.py",
            "--windows-standalone-build",
        )
        return ComfyInstallation(
            root=root,
            comfy_root=comfy_root,
            input_dir=comfy_root / "input",
            output_dir=comfy_root / "output",
            python_executable=python_executable,
            start_command=command,
            portable=True,
        )

    if standard_main.is_file():
        return ComfyInstallation(
            root=root,
            comfy_root=root,
            input_dir=root / "input",
            output_dir=root / "output",
            python_executable=Path(sys.executable).resolve(),
            start_command=(sys.executable, "main.py"),
            portable=False,
        )
    return None


def _dedupe_paths(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        try:
            resolved = value.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return result


def candidate_comfyui_roots(cwd: Path | None = None) -> list[Path]:
    cwd = (cwd or Path.cwd()).resolve()
    home = Path.home()
    candidates: list[Path] = []
    env_root = os.environ.get("COMFYUI_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    candidates.extend(
        [
            cwd,
            cwd / "ComfyUI",
            cwd.parent,
            cwd.parent / "ComfyUI",
            cwd.parent / "ComfyUI_windows_portable",
            home / "ComfyUI",
            home / "ComfyUI_windows_portable",
        ]
    )
    if os.name == "nt":
        for drive in ("C:", "D:", "E:"):
            candidates.extend(
                [
                    Path(f"{drive}/ComfyUI"),
                    Path(f"{drive}/AI/ComfyUI"),
                    Path(f"{drive}/AI/ComfyUI_windows_portable"),
                    Path(f"{drive}/ComfyUI_windows_portable"),
                ]
            )
    return _dedupe_paths(candidates)


def discover_comfyui(cwd: Path | None = None) -> list[ComfyInstallation]:
    installations: list[ComfyInstallation] = []
    seen: set[str] = set()
    for candidate in candidate_comfyui_roots(cwd):
        installation = inspect_comfyui_root(candidate)
        if installation is None:
            continue
        key = os.path.normcase(str(installation.root))
        if key in seen:
            continue
        seen.add(key)
        installations.append(installation)
    return installations


def probe_comfyui(base_url: str = "http://127.0.0.1:8188", timeout: float = 2.0) -> dict[str, Any] | None:
    try:
        with urlopen(base_url.rstrip("/") + "/system_stats", timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _ask(
    prompt: str,
    *,
    input_fn: Callable[[str], str],
    default: str | None = None,
) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input_fn(f"{prompt}{suffix}: ").strip()
    return value if value else (default or "")


def _confirm(
    prompt: str,
    *,
    input_fn: Callable[[str], str],
    default: bool,
) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input_fn(f"{prompt} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true", "是"}


def _default_control_visible_window(existing: Config | None) -> bool:
    if existing is not None:
        return existing.comfyui_visible_window
    return os.name == "nt"


def _choose_existing_config_action(
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> str:
    output_fn("检测到现有配置。")
    output_fn("  [1] 检查并更新")
    output_fn("  [2] 创建新配置（自动备份旧文件）")
    output_fn("  [3] 退出")
    while True:
        choice = _ask("选择操作", input_fn=input_fn)
        if choice in {"1", "2", "3"}:
            return choice
        output_fn("请输入 1、2 或 3。")


def _toml_string(value: str | Path) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _toml_array(values: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def render_config(
    *,
    base_url: str,
    installation: ComfyInstallation,
    auth_provider: str,
    allowed_logins: list[str],
    public_origin: str,
    control_enabled: bool,
    data_dir: Path,
    workflow_dir: Path,
    monitoring_interval: float = 3.0,
    nvidia_smi_timeout: float = 2.0,
    minimum_free_bytes: int = 512 * 1024 * 1024,
    output_reserve_bytes: int = 1024 * 1024 * 1024,
    max_tracked_bytes: int | None = None,
    control_start_command: tuple[str, ...] | None = None,
    control_working_dir: Path | None = None,
    control_visible_window: bool = False,
    control_startup_timeout: float = 120.0,
    control_shutdown_timeout: float = 30.0,
) -> str:
    command = control_start_command or installation.start_command
    working_dir = control_working_dir or installation.root
    lines = [
        "[server]",
        'host = "127.0.0.1"',
        "port = 8190",
        f"public_origin = {_toml_string(public_origin)}",
        "",
        "[auth]",
        f"provider = {_toml_string(auth_provider)}",
        f"allowed_logins = {_toml_array(allowed_logins)}",
        "",
        "[comfyui]",
        f"base_url = {_toml_string(base_url.rstrip('/'))}",
        f"input_dir = {_toml_string(installation.input_dir)}",
        f"output_dir = {_toml_string(installation.output_dir)}",
        'minimum_version = "0.26.0"',
        "",
        "[comfyui.control]",
        f"enabled = {'true' if control_enabled else 'false'}",
        f"working_dir = {_toml_string(working_dir)}",
        f"start_command = {_toml_array(list(command))}",
        f"visible_window = {'true' if control_visible_window else 'false'}",
        f"startup_timeout_seconds = {control_startup_timeout:g}",
        f"shutdown_timeout_seconds = {control_shutdown_timeout:g}",
        "",
        "[storage]",
        f"data_dir = {_toml_string(data_dir)}",
        f"workflow_dir = {_toml_string(workflow_dir)}",
        f"minimum_free_bytes = {minimum_free_bytes}",
        f"output_reserve_bytes = {output_reserve_bytes}",
    ]
    if max_tracked_bytes is not None:
        lines.append(f"max_tracked_bytes = {max_tracked_bytes}")
    lines.extend(
        [
            "",
            "[monitoring]",
            f"interval_seconds = {monitoring_interval:g}",
            f"nvidia_smi_timeout_seconds = {nvidia_smi_timeout:g}",
            "",
        ]
    )
    return "\n".join(lines)


def _write_config(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _choose_installation(
    candidates: list[ComfyInstallation],
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    preferred: ComfyInstallation | None = None,
) -> ComfyInstallation:
    if preferred is not None:
        output_fn(f"使用当前配置的 ComfyUI：{preferred.root}")
        return preferred

    if len(candidates) == 1:
        output_fn(f"检测到 ComfyUI：{candidates[0].root}")
        return candidates[0]

    if candidates:
        output_fn("发现多个可能的 ComfyUI：")
        for index, candidate in enumerate(candidates, start=1):
            kind = "Portable" if candidate.portable else "标准安装"
            output_fn(f"  [{index}] {candidate.root} ({kind})")
        output_fn("  [0] 手动输入")
        while True:
            choice = _ask("选择 ComfyUI", input_fn=input_fn)
            try:
                selected = int(choice)
            except ValueError:
                selected = -1
            if selected == 0:
                break
            if 1 <= selected <= len(candidates):
                return candidates[selected - 1]
            output_fn(f"请输入 0 到 {len(candidates)}。")

    while True:
        value = _ask("请输入 ComfyUI 根目录", input_fn=input_fn)
        installation = inspect_comfyui_root(value)
        if installation is not None:
            return installation
        output_fn("该目录不是可识别的 ComfyUI 根目录；需要 main.py 或 ComfyUI/main.py。")


def _choose_discovered_start_command(
    installation: ComfyInstallation,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> tuple[str, ...]:
    if not installation.portable:
        return installation.start_command
    options = discover_portable_start_options(
        installation.root,
        installation.python_executable,
    )
    if not options:
        return installation.start_command

    if len(options) == 1:
        option = options[0]
        output_fn(f"使用检测到的 ComfyUI 启动脚本：{option.label}")
        return option.command

    output_fn("检测到多个 ComfyUI 启动脚本：")
    for index, option in enumerate(options, start=1):
        output_fn(f"  [{index}] {option.label}")
        output_fn("      " + " ".join(option.command[1:]))
    output_fn("  [0] 使用 Comfy Remote 默认启动命令")
    while True:
        choice = _ask("选择启动方式", input_fn=input_fn)
        try:
            selected = int(choice)
        except ValueError:
            selected = -1
        if selected == 0:
            return installation.start_command
        if 1 <= selected <= len(options):
            return options[selected - 1].command
        output_fn(f"请输入 0 到 {len(options)}。")


def _autostart_registered(config_path: Path) -> bool:
    try:
        return status_autostart(config_path).output.strip() != "not-registered"
    except AutostartError:
        return False


def run_setup(
    config_path: str | Path = "config.toml",
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    config_path = Path(config_path).expanduser().resolve()
    output_fn("Comfy Remote setup")
    output_fn(f"Python: {sys.version.split()[0]}")
    output_fn(f"当前目录: {Path.cwd()}")
    output_fn(f"配置文件: {config_path}")

    existing: Config | None = None
    if config_path.exists():
        choice = _choose_existing_config_action(input_fn=input_fn, output_fn=output_fn)
        if choice == "3":
            return 0
        if choice == "1":
            try:
                existing = load_config(config_path)
            except (OSError, ConfigError) as exc:
                output_fn(f"现有配置无法读取，将重新创建：{exc}")

    running_stats = probe_comfyui(existing.comfyui_base_url if existing else "http://127.0.0.1:8188")
    if running_stats:
        version = running_stats.get("system", {}).get("comfyui_version", "unknown")
        output_fn(f"ComfyUI API: 已连接 ({version})")
    else:
        output_fn("ComfyUI API: 当前未检测到运行中的 127.0.0.1:8188")

    preferred = None
    if existing is not None:
        preferred = inspect_comfyui_root(existing.comfyui_input_dir.parent)
        if preferred is None and existing.comfyui_input_dir.parent.name.lower() == "comfyui":
            preferred = inspect_comfyui_root(existing.comfyui_input_dir.parent.parent)

    installation = _choose_installation(
        discover_comfyui(config_path.parent),
        input_fn=input_fn,
        output_fn=output_fn,
        preferred=preferred,
    )
    installation.input_dir.mkdir(parents=True, exist_ok=True)
    installation.output_dir.mkdir(parents=True, exist_ok=True)
    output_fn(f"ComfyUI 根目录: {installation.root}")
    output_fn(f"输入目录: {installation.input_dir}")
    output_fn(f"输出目录: {installation.output_dir}")

    base_url = existing.comfyui_base_url if existing else "http://127.0.0.1:8188"
    control_default = existing.comfyui_control_enabled if existing else False
    control_enabled = _confirm(
        "允许 Comfy Remote 启动、关闭和重启 ComfyUI",
        input_fn=input_fn,
        default=control_default,
    )
    has_existing_command = bool(
        existing
        and existing.comfyui_control_enabled
        and existing.comfyui_start_command
    )
    control_command = (
        existing.comfyui_start_command
        if has_existing_command
        else installation.start_command
    )
    control_working_dir = (
        existing.comfyui_working_dir
        if existing and existing.comfyui_working_dir
        else installation.root
    )
    visible_window = _default_control_visible_window(existing)
    if control_enabled:
        if not has_existing_command:
            control_command = _choose_discovered_start_command(
                installation,
                input_fn=input_fn,
                output_fn=output_fn,
            )
        output_fn("ComfyUI 启动命令：")
        output_fn("  " + " ".join(control_command))

    tailscale = inspect_tailscale()
    auth_provider = "local"
    allowed_logins: list[str] = []
    public_origin = "http://127.0.0.1:8190"

    if not tailscale.installed:
        output_fn("未检测到 Tailscale。可先完成本地配置，之后重新运行 setup 开启远程访问。")
    elif not tailscale.connected:
        output_fn(
            f"Tailscale 已安装但未连接（BackendState={tailscale.backend_state or 'unknown'}）。"
        )
    elif not tailscale.login_name or not tailscale.public_origin:
        output_fn("Tailscale 已连接，但无法读取登录身份或 MagicDNS 主机名；暂时使用本地模式。")
    else:
        output_fn(f"当前 Tailscale 用户: {tailscale.login_name}")
        if _confirm("启用 Tailscale 远程访问", input_fn=input_fn, default=True):
            auth_provider = "tailscale"
            allowed_logins = [tailscale.login_name]
            public_origin = tailscale.public_origin
            output_fn("正在配置 Tailscale Serve...")
            try:
                enable_serve(8190)
                output_fn(f"远程地址: {public_origin}")
            except TailscaleError as exc:
                output_fn(f"Tailscale Serve 配置未完成: {exc}")
                output_fn("配置已保留；完成 Tailscale 授权后可重新运行 setup。")

    if existing is not None:
        data_dir = existing.data_dir
        workflow_dir = existing.workflow_dir
        monitoring_interval = existing.monitoring_interval
        nvidia_timeout = existing.nvidia_smi_timeout
        minimum_free_bytes = existing.minimum_free_bytes
        output_reserve_bytes = existing.output_reserve_bytes
        max_tracked_bytes = existing.max_tracked_bytes
        startup_timeout = existing.comfyui_startup_timeout
        shutdown_timeout = existing.comfyui_shutdown_timeout
    else:
        data_dir = config_path.parent / "data"
        workflow_dir = config_path.parent / "workflows"
        monitoring_interval = 3.0
        nvidia_timeout = 2.0
        minimum_free_bytes = 512 * 1024 * 1024
        output_reserve_bytes = 1024 * 1024 * 1024
        max_tracked_bytes = None
        startup_timeout = 120.0
        shutdown_timeout = 30.0

    content = render_config(
        base_url=base_url,
        installation=installation,
        auth_provider=auth_provider,
        allowed_logins=allowed_logins,
        public_origin=public_origin,
        control_enabled=control_enabled,
        data_dir=data_dir,
        workflow_dir=workflow_dir,
        monitoring_interval=monitoring_interval,
        nvidia_smi_timeout=nvidia_timeout,
        minimum_free_bytes=minimum_free_bytes,
        output_reserve_bytes=output_reserve_bytes,
        max_tracked_bytes=max_tracked_bytes,
        control_start_command=control_command,
        control_working_dir=control_working_dir,
        control_visible_window=visible_window,
        control_startup_timeout=startup_timeout,
        control_shutdown_timeout=shutdown_timeout,
    )
    _write_config(config_path, content)
    load_config(config_path)
    output_fn(f"✓ 已写入 {config_path}")

    if os.name == "nt":
        keep_autostart = existing is not None and _autostart_registered(config_path)
        if keep_autostart:
            try:
                result = install_autostart(config_path)
                output_fn(result.output or "✓ 已保留 Windows 登录自启动")
            except AutostartError as exc:
                output_fn(f"自动启动更新失败: {exc}")
                output_fn("稍后可运行: comfyui-remote-panel autostart install")
        elif _confirm(
            "Windows 登录后自动启动 Comfy Remote",
            input_fn=input_fn,
            default=True,
        ):
            try:
                result = install_autostart(config_path)
                output_fn(result.output or "✓ 已安装 Windows 登录自启动")
            except AutostartError as exc:
                output_fn(f"自动启动未安装: {exc}")
                output_fn("稍后可运行: comfyui-remote-panel autostart install")

    output_fn("下一步：")
    output_fn("  comfyui-remote-panel doctor")
    output_fn("  comfyui-remote-panel start")
    if auth_provider == "tailscale":
        output_fn(f"  手机访问 {public_origin}")
    return 0
