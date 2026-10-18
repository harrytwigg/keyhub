from keyhub import config, engine, toshy_runtime


def test_ignored_devices_always_include_the_builtins():
    cfg = config.Config()
    # A config.toml written by an older keyhub lists only the 0.1.x name.
    cfg.keyboard.ignore_devices = ["ydotool virtual device", "My Mouse"]
    ignored = engine.ignored_devices(cfg, ["from toshy"])
    assert ignored[0] == "from toshy"
    assert "ydotoold virtual device" in ignored
    assert "My Mouse" in ignored
    assert len(ignored) == len(set(ignored))


def read_kbtype(runtime):
    prefs = toshy_runtime.read_prefs(runtime / toshy_runtime.PREFS_DB)
    return prefs.get("override_kbtype")


def test_clear_forced_kbtype_resets_a_leftover_apple(tmp_path):
    toshy_runtime.sync_prefs(tmp_path, {"override_kbtype": "Apple"})
    assert toshy_runtime.clear_forced_kbtype(tmp_path)
    assert read_kbtype(tmp_path) == "Auto-Adapt"


def test_clear_forced_kbtype_leaves_other_values_alone(tmp_path):
    toshy_runtime.sync_prefs(tmp_path, {"override_kbtype": "Windows"})
    assert not toshy_runtime.clear_forced_kbtype(tmp_path)
    assert read_kbtype(tmp_path) == "Windows"


def test_clear_forced_kbtype_without_a_database(tmp_path):
    assert not toshy_runtime.clear_forced_kbtype(tmp_path)


def test_option_off_restart_clears_a_stale_apple_override(tmp_path):
    toshy_runtime.sync_prefs(tmp_path, {"override_kbtype": "Apple"})
    engine._apply_kbtype_setting(tmp_path, config.Config())
    assert read_kbtype(tmp_path) == "Auto-Adapt"


def test_explicit_override_in_config_is_not_cleared(tmp_path):
    cfg = config.Config(toshy={"override_kbtype": "Apple"})
    toshy_runtime.sync_prefs(tmp_path, cfg.toshy)
    engine._apply_kbtype_setting(tmp_path, cfg)
    assert read_kbtype(tmp_path) == "Apple"
