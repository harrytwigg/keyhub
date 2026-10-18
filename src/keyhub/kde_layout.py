"""Switch KDE's keyboard layout to match the keyboard in use.

An Apple keyboard wants the Macintosh variant of a layout (``gb`` + ``mac``
puts ``@`` on Shift+2) and a laptop's own keyboard the plain one. KDE has one
active layout for the whole session, so keyhub flips between two entries of
the layout list as an Apple keyboard comes and goes. KWin serves this over
D-Bus on both X11 and Wayland, so no session-specific tooling is involved.

The layout list itself is the user's to set up (System Settings, or
``LayoutList`` / ``VariantList`` in ``~/.config/kxkbrc``); keyhub only picks
from it.
"""

from __future__ import annotations

import logging

import dbus

log = logging.getLogger(__name__)

BUS_NAME = "org.kde.keyboard"
OBJECT_PATH = "/Layouts"
INTERFACE = "org.kde.KeyboardLayouts"

# (layout, variant, display name), as KDE's getLayoutsList returns them.
Layout = tuple[str, str, str]


def pick_index(layouts: list[Layout], variant: str, apple: bool) -> int | None:
    """The layout to use: the first ``variant`` one for an Apple keyboard, else the first other.

    None when the list has no such entry.
    """
    for index, (_, layout_variant, _) in enumerate(layouts):
        if (layout_variant == variant) == apple:
            return index
    return None


def _interface(bus=None):
    bus = bus or dbus.bus.BusConnection(dbus.bus.BUS_SESSION)
    return dbus.Interface(bus.get_object(BUS_NAME, OBJECT_PATH, introspect=False), INTERFACE)


def select(apple: bool, variant: str, iface=None) -> None:
    """Make the active KDE layout the one for an Apple (or other) keyboard.

    Raises ``dbus.DBusException`` when KWin isn't reachable, so a caller that
    retries (keyhub's watcher does) copes with KWin starting after keyhub.
    """
    iface = iface or _interface()
    layouts = [(str(lay), str(var), str(name)) for lay, var, name in iface.getLayoutsList()]
    index = pick_index(layouts, variant, apple)
    if index is None:
        log.warning(
            "KDE's layout list has no %s layout; add one (for example %s) to use "
            "apple_layout_variant", "'" + variant + "'" if apple else "non-'" + variant + "'",
            "gb + " + variant,
        )
        return
    if int(iface.getLayout()) != index:
        iface.setLayout(dbus.UInt32(index))
        log.info("keyboard layout: %s", layouts[index][2] or layouts[index][0])
