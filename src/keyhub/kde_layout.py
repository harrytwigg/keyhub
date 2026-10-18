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

import configparser
import logging
import os
from pathlib import Path

import dbus

log = logging.getLogger(__name__)

BUS_NAME = "org.kde.keyboard"
OBJECT_PATH = "/Layouts"
INTERFACE = "org.kde.KeyboardLayouts"
KXKBRC = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kxkbrc"


def configured_variants(path: Path = KXKBRC) -> list[str]:
    """The variant of each entry in KDE's layout list, in list order.

    KWin's ``getLayoutsList`` returns only (layout, display name, description),
    not the variant, so read it from the same ``kxkbrc`` list KWin builds the
    entries from (``VariantList`` lines up with ``LayoutList`` by position).
    """
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str  # keys are case-sensitive
    try:
        parser.read(path, encoding="utf-8")
        layouts = parser.get("Layout", "LayoutList", fallback="").split(",")
        variants = parser.get("Layout", "VariantList", fallback="").split(",")
    except (OSError, configparser.Error):
        return []
    if layouts == [""]:
        return []
    return [v.strip() for v in variants[: len(layouts)]] + [""] * (len(layouts) - len(variants))


def pick_index(variants: list[str], variant: str, apple: bool) -> int | None:
    """The layout to use: the first ``variant`` one for an Apple keyboard, else the first other.

    None when the list has no such entry.
    """
    for index, layout_variant in enumerate(variants):
        if (layout_variant == variant) == apple:
            return index
    return None


def _interface(bus=None):
    bus = bus or dbus.bus.BusConnection(dbus.bus.BUS_SESSION)
    return dbus.Interface(bus.get_object(BUS_NAME, OBJECT_PATH, introspect=False), INTERFACE)


def select(apple: bool, variant: str, iface=None, variants: list[str] | None = None) -> None:
    """Make the active KDE layout the one for an Apple (or other) keyboard.

    Raises ``dbus.DBusException`` when KWin isn't reachable, so a caller that
    retries (keyhub's watcher does) copes with KWin starting after keyhub.
    """
    iface = iface or _interface()
    variants = configured_variants() if variants is None else variants
    names = [str(name) or str(layout) for layout, _, name in iface.getLayoutsList()]
    if len(names) != len(variants):
        log.warning(
            "KDE has %d layouts but %s lists %d; leaving the layout alone",
            len(names), KXKBRC, len(variants),
        )
        return
    index = pick_index(variants, variant, apple)
    if index is None:
        log.warning(
            "KDE's layout list has no %s layout; add both, for example gb and gb (%s), "
            "to use apple_layout_variant", f"'{variant}'" if apple else f"non-'{variant}'", variant,
        )
        return
    if int(iface.getLayout()) != index:
        iface.setLayout(dbus.UInt32(index))
        log.info("keyboard layout: %s", names[index])
