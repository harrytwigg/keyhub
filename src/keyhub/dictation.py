"""The dictation layer: turns hotkeys into Handy commands, before Toshy sees them.

Runs inside the keymapper's input loop, so ``filter()`` must never block. It
makes every swallow/pass decision synchronously from local state, and hands
the actual Handy calls to a worker thread that processes them in order.

Handy only offers *toggle* commands externally, so push-to-talk is emulated as
toggle-on-press / toggle-on-release. A blind toggle can start a recording
nobody asked for (e.g. pressing while Handy is still pasting, then releasing),
so the worker checks Handy's busy state before each toggle.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass

from evdev import ecodes

from . import handy
from .config import DictationConfig
from .hotkeys import Hotkey, parse

log = logging.getLogger(__name__)

RELEASE, PRESS, REPEAT = 0, 1, 2

# Handy debounces presses closer than 30 ms; external toggles count as presses.
MIN_TOGGLE_GAP_S = 0.08
# How long a just-started recording may take to show up as busy in Handy's tray.
START_CONFIRM_S = 1.5
POLL_S = 0.02
AVAILABILITY_REFRESH_S = 2.0


@dataclass(frozen=True, eq=False)
class Binding:
    hotkey: Hotkey
    flag: str  # Handy CLI flag that toggles this kind of dictation


def bindings_from_config(cfg: DictationConfig) -> list[Binding]:
    bindings = [Binding(parse(cfg.hotkey), handy.TOGGLE_TRANSCRIPTION)]
    if cfg.post_process_hotkey:
        bindings.append(Binding(parse(cfg.post_process_hotkey), handy.TOGGLE_POST_PROCESS))
    return bindings


class DictationLayer:
    def __init__(self, bindings, cancel: Hotkey | None, push_to_talk: bool, client,
                 *, threaded: bool = True, clock=time.monotonic, sleep=time.sleep):
        self.bindings = bindings
        self.cancel = cancel
        self.push_to_talk = push_to_talk
        self.client = client
        self._clock, self._sleep = clock, sleep

        # Input-thread state.
        self._held: set[int] = set()
        self._swallowed: dict[int, Binding | None] = {}  # key -> binding it triggered
        self._active: Binding | None = None  # dictation keyhub started and hasn't ended

        # Worker-thread state.
        self._started: Binding | None = None
        self._last_toggle = float("-inf")

        self.available = True  # Handy running; refreshed by the worker
        self._queue: queue.Queue | None = None
        if threaded:
            self._queue = queue.Queue()
            threading.Thread(target=self._run_worker, name="keyhub-dictation", daemon=True).start()

    @classmethod
    def from_config(cls, cfg: DictationConfig, client, **kwargs) -> "DictationLayer":
        cancel = parse(cfg.cancel_key) if cfg.cancel_key else None
        return cls(bindings_from_config(cfg), cancel, cfg.push_to_talk, client, **kwargs)

    # ---- input thread -------------------------------------------------------

    def filter(self, event) -> bool:
        """Observe one input event. Returns True if keyhub consumed it."""
        if event.type != ecodes.EV_KEY:
            return False
        code, value = event.code, event.value

        if value == REPEAT:
            return code in self._swallowed

        if value == PRESS:
            held_before = set(self._held)
            self._held.add(code)
            if not self.available:
                return False
            for binding in self.bindings:
                if binding.hotkey.matches(code, held_before):
                    self._swallowed[code] = binding
                    self._on_hotkey_press(binding)
                    return True
            # Lenient: during push-to-talk the hotkey's modifiers are still held.
            if self._active and self.cancel and self.cancel.matches(code, held_before, exact=False):
                self._swallowed[code] = None
                self._active = None
                self._submit("cancel", None)
                return True
            return False

        # RELEASE
        self._held.discard(code)
        if code not in self._swallowed:
            return False
        binding = self._swallowed.pop(code)
        if binding is not None and self.push_to_talk and self._active is binding:
            self._active = None
            self._submit("stop", binding)
        return True

    def _on_hotkey_press(self, binding: Binding) -> None:
        if self._active is None:
            self._active = binding
            self._submit("start", binding)
        elif not self.push_to_talk and self._active is binding:
            self._active = None
            self._submit("stop", binding)
        # Otherwise another dictation is in progress: swallow and ignore.

    def _submit(self, op: str, binding: Binding | None) -> None:
        if self._queue is None:
            self._handle(op, binding)
        else:
            self._queue.put((op, binding))

    # ---- worker thread ------------------------------------------------------

    def _run_worker(self) -> None:
        self._refresh_availability()
        while True:
            try:
                op, binding = self._queue.get(timeout=AVAILABILITY_REFRESH_S)
            except queue.Empty:
                self._refresh_availability()
                continue
            self._handle(op, binding)

    def _refresh_availability(self) -> None:
        try:
            available = self.client.is_running()
        except Exception as exc:
            log.debug("Handy availability check failed: %s", exc)
            available = False
        if available != self.available:
            log.info("Handy %s", "is running; dictation hotkeys active" if available
                     else "is not running; dictation hotkeys pass through")
        self.available = available

    def _handle(self, op: str, binding: Binding | None) -> None:
        try:
            getattr(self, f"_do_{op}")(binding)
        except Exception:
            log.exception("dictation %s failed", op)

    def _toggle(self, flag: str) -> None:
        gap = self._last_toggle + MIN_TOGGLE_GAP_S - self._clock()
        if gap > 0:
            self._sleep(gap)
        self.client.send(flag)
        self._last_toggle = self._clock()

    def _do_start(self, binding: Binding) -> None:
        if self.client.busy():
            log.info("Handy is still busy; ignoring %s", binding.hotkey.text)
            return
        log.debug("start %s", binding.flag)
        self._toggle(binding.flag)
        self._started = binding

    def _do_stop(self, binding: Binding) -> None:
        if self._started is not binding:
            return
        self._started = None
        if self._wait_until_busy() is False:
            # Never started, or ended elsewhere (tray, Handy's own cancel). A
            # toggle now would start a fresh recording, so do nothing.
            log.info("Handy is not recording; not sending stop")
            return
        log.debug("stop %s", binding.flag)
        self._toggle(binding.flag)

    def _do_cancel(self, _binding: None) -> None:
        self._started = None
        log.debug("cancel")
        self.client.send(handy.CANCEL)

    def _wait_until_busy(self) -> bool | None:
        """Wait for a just-sent start to register. None means Handy has no tray to ask."""
        deadline = self._last_toggle + START_CONFIRM_S
        while True:
            busy = self.client.busy()
            if busy is not False or self._clock() >= deadline:
                return busy
            self._sleep(POLL_S)
