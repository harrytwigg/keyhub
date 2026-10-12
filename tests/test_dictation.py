from types import SimpleNamespace

import pytest
from evdev import ecodes as e

from keyhub import handy
from keyhub.config import DictationConfig
from keyhub.dictation import PRESS, RELEASE, REPEAT, DictationLayer


class FakeHandy:
    """Models Handy's toggle semantics and the busy state its tray exposes."""

    def __init__(self, running=True, has_tray=True):
        self.running = running
        self.has_tray = has_tray
        self.recording = False
        self.processing = False
        self.sent = []

    def is_running(self):
        return self.running

    def send(self, flag):
        self.sent.append(flag)
        if flag == handy.CANCEL:
            self.recording = False
        elif self.recording:
            self.recording, self.processing = False, True
        elif not self.processing:
            self.recording = True

    def busy(self):
        if not self.has_tray:
            return None
        return self.recording or self.processing


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def make_layer(client, **cfg):
    clock = FakeClock()
    return DictationLayer.from_config(
        DictationConfig(hotkey="shift_left+z", **cfg), client,
        threaded=False, clock=clock, sleep=clock.sleep,
    )


def key(code, value):
    return SimpleNamespace(type=e.EV_KEY, code=code, value=value)


def tap(layer, *codes):
    """Press codes in order, release in reverse; return what was swallowed."""
    eaten = [layer.filter(key(c, PRESS)) for c in codes]
    eaten += [layer.filter(key(c, RELEASE)) for c in reversed(codes)]
    return eaten


def test_push_to_talk_starts_on_press_and_stops_on_release():
    client = FakeHandy()
    layer = make_layer(client)
    assert layer.filter(key(e.KEY_LEFTSHIFT, PRESS)) is False
    assert layer.filter(key(e.KEY_Z, PRESS)) is True
    assert client.recording
    assert layer.filter(key(e.KEY_Z, REPEAT)) is True
    assert layer.filter(key(e.KEY_Z, RELEASE)) is True
    assert client.sent == [handy.TOGGLE_TRANSCRIPTION, handy.TOGGLE_TRANSCRIPTION]
    assert client.processing


def test_plain_z_and_other_modifiers_pass_through():
    client = FakeHandy()
    layer = make_layer(client)
    assert tap(layer, e.KEY_Z) == [False, False]
    assert tap(layer, e.KEY_RIGHTSHIFT, e.KEY_Z) == [False] * 4
    assert tap(layer, e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_Z) == [False] * 6
    assert client.sent == []


def test_press_while_handy_is_still_processing_does_not_start_a_stray_recording():
    client = FakeHandy()
    client.processing = True
    layer = make_layer(client)
    assert tap(layer, e.KEY_LEFTSHIFT, e.KEY_Z) == [False, True, True, False]
    assert client.sent == []
    assert not client.recording


def test_release_after_external_cancel_does_not_toggle():
    client = FakeHandy()
    layer = make_layer(client)
    layer.filter(key(e.KEY_LEFTSHIFT, PRESS))
    layer.filter(key(e.KEY_Z, PRESS))
    client.recording = False  # cancelled from Handy's tray
    layer.filter(key(e.KEY_Z, RELEASE))
    assert client.sent == [handy.TOGGLE_TRANSCRIPTION]
    assert not client.recording


def test_cancel_key_only_swallowed_during_dictation():
    client = FakeHandy()
    layer = make_layer(client)
    assert tap(layer, e.KEY_ESC) == [False, False]

    layer.filter(key(e.KEY_LEFTSHIFT, PRESS))
    layer.filter(key(e.KEY_Z, PRESS))
    assert tap(layer, e.KEY_ESC) == [True, True]
    assert client.sent[-1] == handy.CANCEL
    assert not client.recording
    # Releasing the hotkey after a cancel must not start a new recording.
    layer.filter(key(e.KEY_Z, RELEASE))
    assert client.sent == [handy.TOGGLE_TRANSCRIPTION, handy.CANCEL]


def test_toggle_mode():
    client = FakeHandy()
    layer = make_layer(client, push_to_talk=False)
    tap(layer, e.KEY_LEFTSHIFT, e.KEY_Z)
    assert client.recording
    tap(layer, e.KEY_LEFTSHIFT, e.KEY_Z)
    assert client.sent == [handy.TOGGLE_TRANSCRIPTION] * 2
    assert client.processing


def test_post_process_hotkey_uses_its_own_flag():
    client = FakeHandy()
    layer = make_layer(client, post_process_hotkey="ctrl+shift+space")
    tap(layer, e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_SPACE)
    assert client.sent == [handy.TOGGLE_POST_PROCESS, handy.TOGGLE_POST_PROCESS]


def test_keys_pass_through_when_handy_is_not_running():
    client = FakeHandy(running=False)
    layer = make_layer(client)
    layer.available = False
    assert tap(layer, e.KEY_LEFTSHIFT, e.KEY_Z) == [False] * 4
    assert client.sent == []


def test_without_tray_falls_back_to_blind_toggles():
    client = FakeHandy(has_tray=False)
    layer = make_layer(client)
    tap(layer, e.KEY_LEFTSHIFT, e.KEY_Z)
    assert client.sent == [handy.TOGGLE_TRANSCRIPTION] * 2


def test_non_key_events_pass_through():
    layer = make_layer(FakeHandy())
    assert layer.filter(SimpleNamespace(type=e.EV_REL, code=0, value=1)) is False


@pytest.mark.parametrize("delay", [0.0, 0.01])
def test_toggles_are_spaced_beyond_handys_debounce(delay):
    client = FakeHandy()
    layer = make_layer(client)
    times = []
    original = client.send
    client.send = lambda flag: (times.append(layer._clock()), original(flag))
    tap(layer, e.KEY_LEFTSHIFT, e.KEY_Z)
    assert times[1] - times[0] >= 0.03
