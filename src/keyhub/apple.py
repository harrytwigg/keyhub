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

APPLE_NAME = re.compile(r"apple|magic keyboard", re.I)
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


def _read_present(path: Path) -> bool:
    try:
        return apple_keyboard_present(path.read_text(errors="replace"))
    except OSError:
        return False


def watch(
    apply: Callable[[bool], None],
    *,
    path: Path = PROC_DEVICES,
    interval: float = POLL_SECONDS,
    stop: threading.Event | None = None,
) -> threading.Thread:
    """Call ``apply(present)`` now and again whenever an Apple keyboard comes or goes."""
    stop = stop or threading.Event()
    state = _read_present(path)
    apply(state)

    def poll():
        nonlocal state
        while not stop.wait(interval):
            now = _read_present(path)
            if now != state:
                state = now
                log.info("Apple keyboard %s", "connected" if now else "disconnected")
                apply(now)

    thread = threading.Thread(target=poll, name="keyhub-apple", daemon=True)
    thread.start()
    return thread
