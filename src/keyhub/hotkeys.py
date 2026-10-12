"""Parse Handy-style hotkey strings (e.g. ``shift_left+z``) into evdev key codes.

The names follow the ``handy-keys`` crate Handy uses, so bindings copied out
of Handy's settings mean the same thing here.
"""

from __future__ import annotations

from dataclasses import dataclass

from evdev import ecodes as e

_L_R = {
    "shift": (e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT),
    "ctrl": (e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL),
    "alt": (e.KEY_LEFTALT, e.KEY_RIGHTALT),
    "super": (e.KEY_LEFTMETA, e.KEY_RIGHTMETA),
}

_MOD_ALIASES = {
    "shift": "shift",
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "opt": "alt", "option": "alt",
    "super": "super", "cmd": "super", "command": "super", "meta": "super",
    "win": "super", "windows": "super",
}

MODIFIER_CODES = frozenset(code for pair in _L_R.values() for code in pair)


def _modifier_group(name: str) -> frozenset[int] | None:
    """Return the key codes that satisfy a modifier name, or None if not a modifier."""
    if name in ("altgr", "ralt"):
        return frozenset({e.KEY_RIGHTALT})
    for prefix, side in (("l", 0), ("r", 1)):
        # lshift, rctrl, lcmd, ...
        if name.startswith(prefix) and name[1:] in _MOD_ALIASES:
            return frozenset({_L_R[_MOD_ALIASES[name[1:]]][side]})
    for suffix, side in (("left", 0), ("right", 1)):
        base = name.removesuffix("_" + suffix).removesuffix(suffix)
        if base != name and base in _MOD_ALIASES:
            return frozenset({_L_R[_MOD_ALIASES[base]][side]})
    if name in _MOD_ALIASES:
        return frozenset(_L_R[_MOD_ALIASES[name]])
    return None


_KEY_ALIASES = {
    "space": e.KEY_SPACE, " ": e.KEY_SPACE,
    "return": e.KEY_ENTER, "enter": e.KEY_ENTER,
    "escape": e.KEY_ESC, "esc": e.KEY_ESC,
    # handy-keys uses macOS naming: "delete" is the backspace key.
    "delete": e.KEY_BACKSPACE, "backspace": e.KEY_BACKSPACE,
    "forwarddelete": e.KEY_DELETE, "del": e.KEY_DELETE,
    "insert": e.KEY_INSERT, "ins": e.KEY_INSERT,
    "pause": e.KEY_PAUSE, "break": e.KEY_PAUSE,
    "pageup": e.KEY_PAGEUP, "pagedown": e.KEY_PAGEDOWN,
    "left": e.KEY_LEFT, "leftarrow": e.KEY_LEFT,
    "right": e.KEY_RIGHT, "rightarrow": e.KEY_RIGHT,
    "up": e.KEY_UP, "uparrow": e.KEY_UP,
    "down": e.KEY_DOWN, "downarrow": e.KEY_DOWN,
    "-": e.KEY_MINUS, "minus": e.KEY_MINUS,
    "=": e.KEY_EQUAL, "equal": e.KEY_EQUAL, "equals": e.KEY_EQUAL,
    "[": e.KEY_LEFTBRACE, "leftbracket": e.KEY_LEFTBRACE,
    "]": e.KEY_RIGHTBRACE, "rightbracket": e.KEY_RIGHTBRACE,
    "\\": e.KEY_BACKSLASH, "backslash": e.KEY_BACKSLASH,
    ";": e.KEY_SEMICOLON, "semicolon": e.KEY_SEMICOLON,
    "'": e.KEY_APOSTROPHE, "quote": e.KEY_APOSTROPHE,
    ",": e.KEY_COMMA, "comma": e.KEY_COMMA,
    ".": e.KEY_DOT, "period": e.KEY_DOT,
    "/": e.KEY_SLASH, "slash": e.KEY_SLASH,
    "`": e.KEY_GRAVE, "grave": e.KEY_GRAVE, "backtick": e.KEY_GRAVE,
    "capslock": e.KEY_CAPSLOCK,
    "playpause": e.KEY_PLAYPAUSE, "stop": e.KEY_STOPCD,
    "prevtrack": e.KEY_PREVIOUSSONG, "nexttrack": e.KEY_NEXTSONG,
    "fn": e.KEY_FN, "function": e.KEY_FN,
    "keypadenter": e.KEY_KPENTER,
}


def _key_code(name: str) -> int | None:
    if name in _KEY_ALIASES:
        return _KEY_ALIASES[name]
    if name.startswith("num") and name[3:].isdigit():
        name = name[3:]
    if name.startswith("keypad") and name[6:].isdigit():
        return getattr(e, f"KEY_KP{name[6:]}", None)
    code = getattr(e, f"KEY_{name.upper()}", None)
    return code if isinstance(code, int) else None


class HotkeyError(ValueError):
    pass


@dataclass(frozen=True)
class Hotkey:
    text: str
    key: int
    # Each group must have at least one key held; any held modifier outside
    # every group makes the hotkey not match (so Ctrl+Shift+Z != Shift+Z).
    modifiers: tuple[frozenset[int], ...]

    def matches(self, key: int, held: set[int], exact: bool = True) -> bool:
        """Whether pressing ``key`` with ``held`` keys down triggers this hotkey.

        With ``exact=False``, extra held modifiers are allowed.
        """
        if key != self.key:
            return False
        held_mods = (held & MODIFIER_CODES) - {key}
        if not all(group & held_mods for group in self.modifiers):
            return False
        allowed = frozenset().union(*self.modifiers)
        return not exact or held_mods <= allowed


def parse(text: str) -> Hotkey:
    parts = [p.strip().lower() for p in text.split("+")]
    if not text.strip() or any(not p for p in parts):
        raise HotkeyError(f"empty key in hotkey {text!r}")

    *mod_names, key_name = parts
    groups = []
    for name in mod_names:
        group = _modifier_group(name)
        if group is None:
            raise HotkeyError(f"{name!r} in {text!r} is not a modifier")
        groups.append(group)

    key = _key_code(key_name)
    if key is None:
        # A lone modifier (e.g. "ctrl_right") can be the trigger key itself.
        group = _modifier_group(key_name)
        if group is None or len(group) != 1:
            raise HotkeyError(f"unknown key {key_name!r} in {text!r}")
        (key,) = group
    return Hotkey(text, key, tuple(groups))
