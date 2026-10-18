"""Skip the Toshy keymaps while no Apple keyboard is connected.

Toshy turns a PC keyboard into a Mac-style one (Cmd shortcuts, remapped
modifiers). Without an Apple keyboard plugged in that is unwanted on a
laptop's own keyboard, so keyhub can hand its key events straight to the
virtual keyboard instead, leaving a plain PC keyboard. Dictation hotkeys are
checked before this, so dictation still works.
"""

from __future__ import annotations

from evdev import ecodes

from .apple import APPLE_NAME

PRESS, RELEASE = 1, 0


class Passthrough:
    """Decides, per key, whether its events bypass the keymaps.

    Whether to bypass changes whenever an Apple keyboard comes or goes, but a
    key already held keeps the route it was pressed with, so a press never
    gets its release (or repeats) from a different route: that would leave a
    remapped modifier stuck. Routes are tracked per device, so the same key
    held on two keyboards across a switch can't mix them up.

    An Apple keyboard itself is never bypassed. The decision follows the
    keyboard list with a delay of a few seconds, and right after one is
    plugged in (or wakes from sleep) its first keystrokes must still get the
    Mac keymaps.
    """

    def __init__(self) -> None:
        self.wanted = False
        self._route: dict[tuple[str, int], bool] = {}

    def want(self, bypass: bool) -> None:
        self.wanted = bypass

    def bypass(self, event, device) -> bool:
        """Whether this event should skip the keymaps.

        Non-key events return False: the keymapper forwards those untouched
        anyway, so both routes treat them the same.
        """
        if event.type != ecodes.EV_KEY:
            return False
        if APPLE_NAME.search(getattr(device, "name", "") or ""):
            return False
        slot = (str(getattr(device, "path", "")), event.code)
        if event.value == PRESS or slot not in self._route:
            self._route[slot] = self.wanted
        route = self._route[slot]
        if event.value == RELEASE:
            del self._route[slot]
        return route
