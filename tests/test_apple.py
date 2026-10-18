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
