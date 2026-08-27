from __future__ import annotations

import locale as system_locale
import os
import re
from typing import Callable

SUPPORTED_LANGUAGES = ("en", "zh-CN")

_EN_EXACT = {
    "Comfy Remote setup": "Comfy Remote setup",
    "检测到现有配置。": "Existing configuration detected.",
    "  [1] 检查并更新": "  [1] Check and update",
    "  [2] 创建新配置（自动备份旧文件）": "  [2] Create a new configuration (back up the old file automatically)",
    "  [3] 退出": "  [3] Exit",
    "选择操作": "Choose action",
    "请输入 1、2 或 3。": "Enter 1, 2, or 3.",
    "发现多个可能的 ComfyUI：": "Multiple possible ComfyUI installations found:",
    "标准安装": "standard install",
    "  [0] 手动输入": "  [0] Enter a path manually",
    "选择 ComfyUI": "Choose ComfyUI",
    "请输入 ComfyUI 根目录": "Enter the ComfyUI root directory",
    "该目录不是可识别的 ComfyUI 根目录；需要 main.py 或 ComfyUI/main.py。": "This is not a recognized ComfyUI root; main.py or ComfyUI/main.py is required.",
    "检测到多个 ComfyUI 启动脚本：": "Multiple ComfyUI launch scripts detected:",
    "  [0] 使用 Comfy Remote 默认启动命令": "  [0] Use the Comfy Remote default launch command",
    "选择启动方式": "Choose launch method",
    "允许 Comfy Remote 启动、关闭和重启 ComfyUI": "Allow Comfy Remote to start, stop, and restart ComfyUI",
    "启用 Tailscale 远程访问": "Enable Tailscale remote access",
    "Windows 登录后自动启动 Comfy Remote": "Start Comfy Remote after Windows login",
    "Comfy Remote 已运行": "Comfy Remote is already running",
    "Comfy Remote 已启动": "Comfy Remote started",
    "Comfy Remote 已停止": "Comfy Remote stopped",
    "Comfy Remote 未运行": "Comfy Remote is not running",
    "Comfy Remote 已重启": "Comfy Remote restarted",
}

_ZH_EXACT = {
    "Core": "核心",
    "ComfyUI": "ComfyUI",
    "Remote access": "远程访问",
    "Workflow compatibility": "工作流兼容性",
    "Overall": "总体",
    "data directory": "数据目录",
    "input directory": "输入目录",
    "output directory": "输出目录",
    "running": "运行中",
    "stopped": "已停止",
    "writable": "可写",
    "not writable": "不可写",
    "readable": "可读",
    "not readable": "不可读",
    "available": "可用",
    "unavailable": "不可用",
    "not found": "未找到",
    "not configured": "未配置",
    "connected": "已连接",
    "not connected": "未连接",
    "unknown": "未知",
}


def normalize_language(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("_", "-")
    if raw.startswith("zh"):
        return "zh-CN"
    return "en"


def resolve_language(explicit: str | None = None) -> str:
    if explicit and explicit != "auto":
        return normalize_language(explicit)
    env = os.environ.get("COMFY_REMOTE_LANG")
    if env:
        return normalize_language(env)
    try:
        detected = system_locale.getlocale()[0] or ""
    except ValueError:
        detected = ""
    if not detected:
        detected = os.environ.get("LANG", "")
    return normalize_language(detected)


def _translate_en(text: str) -> str:
    if text in _EN_EXACT:
        return _EN_EXACT[text]
    patterns: list[tuple[str, Callable[[re.Match[str]], str]]] = [
        (r"^当前目录: (.+)$", lambda m: f"Current directory: {m.group(1)}"),
        (r"^配置文件: (.+)$", lambda m: f"Configuration file: {m.group(1)}"),
        (r"^现有配置无法读取，将重新创建：(.+)$", lambda m: f"Existing configuration could not be read and will be recreated: {m.group(1)}"),
        (r"^ComfyUI API: 已连接 \((.+)\)$", lambda m: f"ComfyUI API: connected ({m.group(1)})"),
        (r"^ComfyUI API: 当前未检测到运行中的 127\.0\.0\.1:8188$", lambda m: "ComfyUI API: no running service detected at 127.0.0.1:8188"),
        (r"^使用当前配置的 ComfyUI：(.+)$", lambda m: f"Using configured ComfyUI: {m.group(1)}"),
        (r"^检测到 ComfyUI：(.+)$", lambda m: f"Detected ComfyUI: {m.group(1)}"),
        (r"^请输入 0 到 (\d+)。$", lambda m: f"Enter a number from 0 to {m.group(1)}."),
        (r"^使用检测到的 ComfyUI 启动脚本：(.+)$", lambda m: f"Using detected ComfyUI launch script: {m.group(1)}"),
        (r"^ComfyUI 根目录: (.+)$", lambda m: f"ComfyUI root: {m.group(1)}"),
        (r"^输入目录: (.+)$", lambda m: f"Input directory: {m.group(1)}"),
        (r"^输出目录: (.+)$", lambda m: f"Output directory: {m.group(1)}"),
        (r"^Tailscale: (.+)$", lambda m: f"Tailscale: {m.group(1)}"),
        (r"^远程地址: (.+)$", lambda m: f"Remote URL: {m.group(1)}"),
        (r"^配置已写入: (.+)$", lambda m: f"Configuration written: {m.group(1)}"),
        (r"^备份: (.+)$", lambda m: f"Backup: {m.group(1)}"),
    ]
    for pattern, formatter in patterns:
        match = re.match(pattern, text)
        if match:
            return formatter(match)
    return text


def _translate_zh(text: str) -> str:
    if text in _ZH_EXACT:
        return _ZH_EXACT[text]
    result = text
    replacements = (
        ("not found", "未找到"),
        ("not writable", "不可写"),
        ("writable", "可写"),
        ("not readable", "不可读"),
        ("readable", "可读"),
        ("not configured", "未配置"),
        ("not connected", "未连接"),
        ("connected", "已连接"),
        ("available", "可用"),
        ("unavailable", "不可用"),
        ("running", "运行中"),
        ("stopped", "已停止"),
    )
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def translate_cli(text: str, language: str) -> str:
    value = str(text)
    return _translate_zh(value) if normalize_language(language) == "zh-CN" else _translate_en(value)


def translate_multiline(text: str, language: str) -> str:
    return "\n".join(translate_cli(line, language) for line in str(text).splitlines())


def translated_output(output_fn: Callable[[str], None], language: str) -> Callable[[str], None]:
    def emit(value: str) -> None:
        output_fn(translate_cli(value, language))
    return emit


def translated_input(input_fn: Callable[[str], str], language: str) -> Callable[[str], str]:
    def ask(prompt: str) -> str:
        return input_fn(translate_cli(prompt, language))
    return ask
