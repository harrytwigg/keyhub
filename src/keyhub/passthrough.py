"""Skip the Toshy keymaps while no Apple keyboard is connected.

Toshy turns a PC keyboard into a Mac-style one (Cmd shortcuts, remapped
modifiers). Without an Apple keyboard plugged in that is unwanted on a
laptop's own keyboard, so keyhub can hand its key events straight to the
virtual keyboard instead, leaving a plain PC keyboard. Dictation hotkeys are
checked before this, so dictation still works.
"""

from __future__ import annotations

from evdev import ecodes

PRESS, RELEASE = 1, 0


class Passthrough:
    """Decides, per key, whether its events bypass the keymaps.

    Whether to bypass changes whenever an Apple keyboard comes or goes, but a
    key already held keeps the route it was pressed with, so a press never
    gets its release (or repeats) from a different route: that would leave a
    remapped modifier stuck down.
    """

    def __init__(self) -> None:
        self.wanted = False
        self._route: dict[int, bool] = {}

    def want(self, bypass: bool) -> None:
        self.wanted = bypass

    def bypass(self, event) -> bool:
        """Whether this event should skip the keymaps.

        Non-key events return False: the keymapper forwards those untouched
        anyway, so both routes treat them the same.
        """
        if event.type != ecodes.EV_KEY:
            return False
        if event.value == PRESS or event.code not in self._route:
            self._route[event.code] = self.wanted
        route = self._route[event.code]
        if event.value == RELEASE:
            del self._route[event.code]
        return route
