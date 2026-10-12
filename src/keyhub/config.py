"""keyhub's single config file: ``~/.config/keyhub/config.toml``.

Everything keyboard-related lives here: the dictation hotkeys (which Handy no
longer listens for itself), devices keyhub must never grab, and the Toshy
preferences. Nothing else is allowed to own keyboard config, so there is
exactly one place to look when a shortcut misbehaves.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "keyhub"
CONFIG_PATH = CONFIG_DIR / "config.toml"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "keyhub"

# Handy pastes by typing Ctrl+V through ydotool's virtual keyboard. If keyhub
# grabbed that device, Toshy would remap the paste keystroke.
DEFAULT_IGNORE_DEVICES = ["ydotool virtual device"]


@dataclass
class DictationConfig:
    enabled: bool = True
    hotkey: str = "ctrl+space"
    post_process_hotkey: str = ""
    cancel_key: str = "escape"
    push_to_talk: bool = True


@dataclass
class KeyboardConfig:
    ignore_devices: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_DEVICES))


@dataclass
class Config:
    dictation: DictationConfig = field(default_factory=DictationConfig)
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)
    # Toshy preference name -> value, as stored in Toshy's preferences database.
    toshy: dict[str, str] = field(default_factory=dict)
    verbose: bool = False


class ConfigError(ValueError):
    pass


def _section(data: dict, name: str, cls):
    raw = data.get(name, {})
    known = cls.__dataclass_fields__
    unknown = set(raw) - set(known)
    if unknown:
        raise ConfigError(f"[{name}] has unknown keys: {', '.join(sorted(unknown))}")
    return cls(**raw)


def parse(data: dict) -> Config:
    unknown = set(data) - {"dictation", "keyboard", "toshy", "verbose"}
    if unknown:
        raise ConfigError(f"unknown top-level keys: {', '.join(sorted(unknown))}")
    return Config(
        dictation=_section(data, "dictation", DictationConfig),
        keyboard=_section(data, "keyboard", KeyboardConfig),
        # Toshy stores booleans as the strings 'True' / 'False'.
        toshy={k: str(v) for k, v in data.get("toshy", {}).items()},
        verbose=bool(data.get("verbose", False)),
    )


def load(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    with path.open("rb") as f:
        return parse(tomllib.load(f))


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toshy_toml_value(value: str):
    if value in ("True", "False"):
        return value == "True"
    return value


def render(cfg: Config) -> str:
    d = cfg.dictation
    lines = [
        "# keyhub: the only process that reads your keyboard.",
        "# Edit this file, then: systemctl --user restart keyhub",
        "",
        "# Hotkeys use Handy's key names and refer to the physical keys you press,",
        "# before any Toshy remapping. Handy itself no longer listens for them.",
        "[dictation]",
        f"enabled = {_toml_value(d.enabled)}",
        f"hotkey = {_toml_value(d.hotkey)}",
        "# Empty string disables the post-processing hotkey.",
        f"post_process_hotkey = {_toml_value(d.post_process_hotkey)}",
        "# Only intercepted while a keyhub-started dictation is active.",
        f"cancel_key = {_toml_value(d.cancel_key)}",
        "# true: hold the hotkey to record. false: press once to start, again to stop.",
        f"push_to_talk = {_toml_value(d.push_to_talk)}",
        "",
        "[keyboard]",
        "# Devices keyhub must never grab (name, /dev/input path, or by-id path).",
        f"ignore_devices = {_toml_value(cfg.keyboard.ignore_devices)}",
        "",
        "# Toshy preferences (same names as Toshy's preferences app).",
        "[toshy]",
    ]
    lines += [f"{k} = {_toml_value(_toshy_toml_value(v))}" for k, v in sorted(cfg.toshy.items())]
    return "\n".join(lines) + "\n"


def save(cfg: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(cfg))
