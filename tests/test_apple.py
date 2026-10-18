import threading

from keyhub import apple, config

BUILT_IN = """\
I: Bus=0011 Vendor=0001 Product=0001 Version=ab41
N: Name="AT Translated Set 2 keyboard"
H: Handlers=sysrq kbd event2 leds
"""

MAGIC_KEYBOARD = """\
I: Bus=0005 Vendor=004c Product=0267 Version=0001
N: Name="Apple Inc. Magic Keyboard"
H: Handlers=sysrq kbd event19 leds
"""

MAGIC_TRACKPAD = """\
I: Bus=0005 Vendor=004c Product=0265 Version=0001
N: Name="Apple Inc. Magic Trackpad"
H: Handlers=mouse2 event20
"""

AIRPODS = """\
I: Bus=0005 Vendor=004c Product=2014 Version=0001
N: Name="Someone's AirPods Pro #2 - Find My (AVRCP)"
H: Handlers=kbd event24
"""


def devices(*blocks):
    return "\n".join(blocks)


def test_built_in_keyboard_alone_is_not_apple():
    assert not apple.apple_keyboard_present(devices(BUILT_IN))


def test_magic_keyboard_is_detected():
    assert apple.apple_keyboard_present(devices(BUILT_IN, MAGIC_KEYBOARD))


def test_bluetooth_name_without_apple_prefix():
    named = MAGIC_KEYBOARD.replace("Apple Inc. Magic Keyboard", "Harry's Magic Keyboard")
    assert apple.apple_keyboard_present(devices(named))


def test_apple_pointing_device_does_not_count():
    assert not apple.apple_keyboard_present(devices(BUILT_IN, MAGIC_TRACKPAD))


def named(name):
    return f'I: Bus=0003\nN: Name="{name}"\nH: Handlers=sysrq kbd event3 leds\n'


def test_apple_must_be_a_whole_word():
    for name in ("Pineapple Keyboard", "Snapple Gaming Keyboard", "Grapple Pro"):
        assert not apple.apple_keyboard_present(named(name)), name


def test_apple_names_that_count():
    for name in ("Apple Inc. Magic Keyboard", "Apple Internal Keyboard / Trackpad",
                 "Magic Keyboard with Touch ID", "Harry's Magic Keyboard", "MagicKeyboard"):
        assert apple.apple_keyboard_present(named(name)), name


def test_other_vendors_with_a_kbd_handler_do_not_count():
    assert not apple.apple_keyboard_present(devices(BUILT_IN, AIRPODS))


def test_empty_input():
    assert not apple.apple_keyboard_present("")


def test_kbtype_for():
    assert apple.kbtype_for(True, "Auto-Adapt") == "Apple"
    assert apple.kbtype_for(False, "Auto-Adapt") == "Auto-Adapt"
    # A fixed Toshy type the user chose comes back when the Apple keyboard goes.
    assert apple.kbtype_for(False, "Windows") == "Windows"


def test_watch_applies_now_and_on_change(tmp_path):
    path = tmp_path / "devices"
    path.write_text(devices(BUILT_IN))
    seen, changed, stop = [], threading.Event(), threading.Event()

    def record(present):
        seen.append(present)
        if len(seen) > 1:
            changed.set()

    thread = apple.watch(record, path=path, interval=0.01, stop=stop)
    assert seen == [False]

    path.write_text(devices(BUILT_IN, MAGIC_KEYBOARD))
    assert changed.wait(2)
    assert seen == [False, True]

    changed.clear()
    path.write_text(devices(BUILT_IN))
    assert changed.wait(2)
    assert seen == [False, True, False]

    stop.set()
    thread.join(2)
    assert not thread.is_alive()


def test_watch_survives_unreadable_devices_file(tmp_path):
    seen = []
    stop = threading.Event()
    thread = apple.watch(seen.append, path=tmp_path / "missing", interval=0.01, stop=stop)
    stop.set()
    thread.join(2)
    assert seen == [False]


def test_config_option_round_trips(tmp_path):
    cfg = config.Config()
    assert cfg.keyboard.apple_when_present is False
    cfg.keyboard.apple_when_present = True
    path = tmp_path / "config.toml"
    config.save(cfg, path)
    assert config.load(path).keyboard.apple_when_present is True


def test_ydotoold_device_is_ignored_by_default():
    assert "ydotoold virtual device" in config.Config().keyboard.ignore_devices


def run_watch(path, apply, interval=0.01):
    stop = threading.Event()
    thread = apple.watch(apply, path=path, interval=interval, stop=stop)
    return thread, stop


def test_failing_apply_is_retried_and_the_watcher_survives(tmp_path):
    path = tmp_path / "devices"
    path.write_text(devices(BUILT_IN))
    calls, retried, done = [], threading.Event(), threading.Event()
    failures_left = {False: 1, True: 1}  # each state's first apply hits a "locked" database

    def flaky(present):
        calls.append(present)
        if failures_left[present]:
            failures_left[present] -= 1
            raise RuntimeError("database is locked")
        (done if present else retried).set()

    thread, stop = run_watch(path, flaky)
    assert retried.wait(2)  # the failed initial apply was retried on a later poll
    path.write_text(devices(BUILT_IN, MAGIC_KEYBOARD))
    assert done.wait(2)
    assert thread.is_alive()
    stop.set()
    thread.join(2)
    # Each state failed once, was retried on a later poll, then stuck.
    assert calls == [False, False, True, True]


def test_unreadable_devices_file_keeps_the_last_state(tmp_path):
    path = tmp_path / "devices"
    path.write_text(devices(BUILT_IN, MAGIC_KEYBOARD))
    calls, applied_once = [], threading.Event()

    def record(present):
        calls.append(present)
        applied_once.set()

    thread, stop = run_watch(path, record)
    assert applied_once.wait(2)
    path.unlink()  # transient read failure while the keyboard is still plugged in
    stop.wait(0.1)
    assert calls == [True]
    stop.set()
    thread.join(2)


def test_config_layout_variant_round_trips(tmp_path):
    cfg = config.Config()
    assert cfg.keyboard.apple_layout_variant == ""
    cfg.keyboard.apple_layout_variant = "mac"
    path = tmp_path / "config.toml"
    config.save(cfg, path)
    assert config.load(path).keyboard.apple_layout_variant == "mac"


def test_repeated_failures_log_one_traceback_then_one_liners(tmp_path, caplog):
    path = tmp_path / "devices"
    path.write_text(devices(BUILT_IN))
    attempts, enough, stop = [], threading.Event(), threading.Event()

    def always_fails(present):
        attempts.append(present)
        if len(attempts) >= 4:
            enough.set()
        raise RuntimeError("KWin not running")

    thread = apple.watch(always_fails, path=path, interval=0.01, stop=stop)
    assert enough.wait(2)
    stop.set()
    thread.join(2)
    tracebacks = [r for r in caplog.records if r.exc_info]
    assert len(tracebacks) == 1
    assert any("still can't apply" in r.getMessage() for r in caplog.records)
