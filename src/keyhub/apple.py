"""Switch Toshy to its Apple keyboard type while an Apple keyboard is connected.

Toshy normally adapts to each keyboard on its own, so an Apple keyboard is
Apple-typed and the laptop's built-in one is Windows-typed. With
``apple_when_present`` keyhub instead forces the Apple type for *every*
keyboard for as long as an Apple keyboard is plugged in, and goes back to
Toshy's own choice when it is unplugged. Toshy watches its preferences
database and reloads on change, so nothing restarts.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

PROC_DEVICES = Path("/proc/bus/input/devices")
POLL_SECONDS = 2.0

# Whole words, so "Pineapple Keyboard" and "Grapple Pro" don't count.
APPLE_NAME = re.compile(r"\bapple\b|\bmagic\s*keyboard\b", re.I)
APPLE_KBTYPE = "Apple"


def apple_keyboard_present(devices_text: str) -> bool:
    """Whether /proc/bus/input/devices lists an Apple keyboard.

    Trackpads and mice also carry Apple names, so a device only counts when
    the kernel gave it a keyboard (``kbd``) handler.
    """
    for block in devices_text.split("\n\n"):
        name, handlers = "", []
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("H: Handlers="):
                handlers = line.split("=", 1)[1].split()
        if "kbd" in handlers and APPLE_NAME.search(name):
            return True
    return False


def kbtype_for(present: bool, fallback: str) -> str:
    """The Toshy ``override_kbtype`` to use: Apple while one is plugged in."""
    return APPLE_KBTYPE if present else fallback


def _read_present(path: Path) -> bool | None:
    """True/False from the device list, or None when it can't be read."""
    try:
        return apple_keyboard_present(path.read_text(errors="replace"))
    except OSError:
        return None


def watch(
    apply: Callable[[bool], None],
    *,
    path: Path = PROC_DEVICES,
    interval: float = POLL_SECONDS,
    stop: threading.Event | None = None,
) -> threading.Thread:
    """Call ``apply(present)`` now and again whenever an Apple keyboard comes or goes.

    A failing ``apply`` is logged and retried on the next poll, so a transient
    error (say a locked preferences database) never ends the watcher or
    aborts startup. An unreadable device list keeps the last known state
    rather than being mistaken for an unplug.
    """
    stop = stop or threading.Event()
    applied: bool | None = None
    failing = False

    def sync(present: bool) -> None:
        nonlocal applied, failing
        if present == applied:
            return
        try:
            apply(present)
        except Exception as exc:
            # Full traceback once per run of failures, then one line per retry.
            if failing:
                log.warning("still can't apply the keyboard setting (%s); retrying", exc)
            else:
                log.exception("could not apply the keyboard setting; retrying in %ss", interval)
            failing = True
            return
        failing = False
        if applied is not None:
            log.info("Apple keyboard %s", "connected" if present else "disconnected")
        applied = present

    first = _read_present(path)
    sync(bool(first))

    def poll() -> None:
        while not stop.wait(interval):
            present = _read_present(path)
            if present is not None:
                sync(present)

    thread = threading.Thread(target=poll, name="keyhub-apple", daemon=True)
    thread.start()
    return thread
