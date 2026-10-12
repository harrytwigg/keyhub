import pytest
from evdev import ecodes as e

from keyhub import config
from keyhub.hotkeys import HotkeyError, parse


@pytest.mark.parametrize("text, key, mods", [
    ("shift_left+z", e.KEY_Z, [{e.KEY_LEFTSHIFT}]),
    ("ctrl+shift+space", e.KEY_SPACE,
     [{e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL}, {e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT}]),
    ("escape", e.KEY_ESC, []),
    ("ctrl_right", e.KEY_RIGHTCTRL, []),
    ("cmd_left+f13", e.KEY_F13, [{e.KEY_LEFTMETA}]),
    ("Option+Delete", e.KEY_BACKSPACE, [{e.KEY_LEFTALT, e.KEY_RIGHTALT}]),
    ("altgr+keypad5", e.KEY_KP5, [{e.KEY_RIGHTALT}]),
])
def test_parse(text, key, mods):
    hotkey = parse(text)
    assert hotkey.key == key
    assert [set(g) for g in hotkey.modifiers] == mods


@pytest.mark.parametrize("text", ["", "ctrl+", "z+ctrl", "hyper+z", "ctrl+nosuchkey"])
def test_parse_errors(text):
    with pytest.raises(HotkeyError):
        parse(text)


def test_match_requires_exact_modifiers():
    hotkey = parse("ctrl+shift+space")
    assert hotkey.matches(e.KEY_SPACE, {e.KEY_RIGHTCTRL, e.KEY_LEFTSHIFT})
    assert not hotkey.matches(e.KEY_SPACE, {e.KEY_LEFTCTRL})
    assert not hotkey.matches(e.KEY_SPACE, {e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_LEFTALT})
    # Non-modifier keys held at the same time don't matter.
    assert hotkey.matches(e.KEY_SPACE, {e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_A})


def test_config_round_trip(tmp_path):
    cfg = config.Config()
    cfg.dictation.hotkey = "shift_left+z"
    cfg.dictation.post_process_hotkey = 'ctrl+"'
    cfg.toshy = {"capslock_mode": "caps_is_caps", "forced_numpad": "True"}
    path = tmp_path / "config.toml"
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_config_rejects_unknown_keys():
    with pytest.raises(config.ConfigError):
        config.parse({"dictation": {"hotky": "z"}})


def test_missing_config_gives_defaults(tmp_path):
    assert config.load(tmp_path / "nope.toml") == config.Config()
