from types import SimpleNamespace

from evdev import ecodes as e

from keyhub import apple, config, engine
from keyhub.passthrough import Passthrough

DOWN, UP, REPEAT = 1, 0, 2

BUILT_IN = SimpleNamespace(name="AT Translated Set 2 keyboard", path="/dev/input/event2")
MAGIC = SimpleNamespace(name="Apple Inc. Magic Keyboard", path="/dev/input/event19")
OTHER = SimpleNamespace(name="Some USB Keyboard", path="/dev/input/event30")


def key(code, value):
    return SimpleNamespace(type=e.EV_KEY, code=code, value=value)


def bypass(p, event, device=BUILT_IN):
    return p.bypass(event, device)


def test_nothing_bypasses_by_default():
    p = Passthrough()
    assert not bypass(p, key(e.KEY_C, DOWN))


def test_wanted_bypass_applies_to_new_presses():
    p = Passthrough()
    p.want(True)
    assert bypass(p, key(e.KEY_C, DOWN))
    assert bypass(p, key(e.KEY_C, REPEAT))
    assert bypass(p, key(e.KEY_C, UP))


def test_non_key_events_never_bypass():
    p = Passthrough()
    p.want(True)
    assert not bypass(p, SimpleNamespace(type=e.EV_SYN, code=0, value=0))
    assert not bypass(p, SimpleNamespace(type=e.EV_MSC, code=e.MSC_SCAN, value=1))


def test_a_held_key_keeps_the_route_it_was_pressed_with():
    p = Passthrough()
    assert not bypass(p, key(e.KEY_LEFTCTRL, DOWN))   # pressed while keymaps are on
    p.want(True)                                     # the Apple keyboard is unplugged
    assert not bypass(p, key(e.KEY_LEFTCTRL, REPEAT))
    assert not bypass(p, key(e.KEY_LEFTCTRL, UP))     # release follows the press: no stuck key
    assert bypass(p, key(e.KEY_LEFTCTRL, DOWN))       # the next press takes the new route


def test_a_held_bypassed_key_is_released_through_the_bypass_when_keymaps_return():
    p = Passthrough()
    p.want(True)
    assert bypass(p, key(e.KEY_A, DOWN))
    p.want(False)                                    # an Apple keyboard is plugged in
    assert bypass(p, key(e.KEY_A, UP))
    assert not bypass(p, key(e.KEY_A, DOWN))


def test_a_release_with_no_press_uses_the_current_route():
    p = Passthrough()
    p.want(True)
    assert bypass(p, key(e.KEY_B, UP))


def test_keys_are_routed_independently():
    p = Passthrough()
    assert not bypass(p, key(e.KEY_LEFTMETA, DOWN))
    p.want(True)
    assert bypass(p, key(e.KEY_C, DOWN))
    assert not bypass(p, key(e.KEY_LEFTMETA, UP))
    assert bypass(p, key(e.KEY_C, UP))


def run_watch_apply(monkeypatch, tmp_path, **keyboard):
    """Start the engine's Apple watcher with a captured `apply`, returning (apply, passthrough, prefs)."""
    captured, prefs = {}, []
    monkeypatch.setattr(apple, "watch", lambda apply: captured.setdefault("apply", apply))
    monkeypatch.setattr(engine.toshy_runtime, "sync_prefs", lambda runtime, p: prefs.append(p))
    monkeypatch.setattr(engine.kde_layout, "select", lambda *a: prefs.append(("layout", a)))
    cfg = config.Config()
    for name, value in keyboard.items():
        setattr(cfg.keyboard, name, value)
    passthrough = Passthrough()
    engine._apply_kbtype_setting(tmp_path, cfg, passthrough)
    return captured.get("apply"), passthrough, prefs


def test_option_alone_only_drives_the_bypass(monkeypatch, tmp_path):
    apply, passthrough, prefs = run_watch_apply(monkeypatch, tmp_path, passthrough_without_apple=True)
    apply(False)
    assert passthrough.wanted is True
    apply(True)
    assert passthrough.wanted is False
    assert prefs == []  # neither Toshy's kbtype nor the layout was touched


def test_apple_type_and_layout_do_not_enable_the_bypass(monkeypatch, tmp_path):
    apply, passthrough, prefs = run_watch_apply(
        monkeypatch, tmp_path, apple_when_present=True, apple_layout_variant="mac")
    apply(False)
    assert passthrough.wanted is False
    assert prefs[0] == {"override_kbtype": "Auto-Adapt"}
    assert prefs[1][0] == "layout"


def test_layout_variant_works_without_apple_when_present(monkeypatch, tmp_path):
    apply, _, prefs = run_watch_apply(monkeypatch, tmp_path, apple_layout_variant="mac")
    apply(True)
    assert prefs == [("layout", (True, "mac"))]


def test_no_watcher_when_no_option_is_set(monkeypatch, tmp_path):
    apply, _, _ = run_watch_apply(monkeypatch, tmp_path)
    assert apply is None


def test_config_option_round_trips(tmp_path):
    cfg = config.Config()
    assert cfg.keyboard.passthrough_without_apple is False
    cfg.keyboard.passthrough_without_apple = True
    path = tmp_path / "config.toml"
    config.save(cfg, path)
    assert config.load(path).keyboard.passthrough_without_apple is True


def test_an_apple_keyboard_is_never_bypassed_even_while_wanted():
    p = Passthrough()
    p.want(True)  # e.g. the poll hasn't noticed the Magic Keyboard waking up yet
    assert not p.bypass(key(e.KEY_LEFTMETA, DOWN), MAGIC)
    assert not p.bypass(key(e.KEY_C, DOWN), MAGIC)
    assert not p.bypass(key(e.KEY_C, UP), MAGIC)
    assert p.bypass(key(e.KEY_C, DOWN), BUILT_IN)


def test_the_same_key_held_on_two_keyboards_keeps_separate_routes():
    p = Passthrough()
    assert not p.bypass(key(e.KEY_LEFTSHIFT, DOWN), BUILT_IN)   # keymaps on
    p.want(True)
    assert p.bypass(key(e.KEY_LEFTSHIFT, DOWN), OTHER)           # same key, other device, bypass
    assert not p.bypass(key(e.KEY_LEFTSHIFT, UP), BUILT_IN)      # first release: its own route
    assert p.bypass(key(e.KEY_LEFTSHIFT, UP), OTHER)


def test_unnamed_device_is_handled():
    p = Passthrough()
    p.want(True)
    assert p.bypass(key(e.KEY_A, DOWN), None)
