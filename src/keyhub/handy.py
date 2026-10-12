"""Control a running Handy instance over D-Bus, without touching the keyboard.

Handy exposes two things keyhub uses:

* ``com.pais.handy.SingleInstance``: the endpoint ``handy --toggle-transcription``
  and friends forward their argv to. Calling it directly skips spawning a
  second Handy process for every key press.
* Its tray menu (StatusNotifierItem + dbusmenu). Handy swaps the model submenu
  for a "Cancel" item while it is recording or transcribing, which is the only
  externally visible busy/idle signal. Checking for the submenu (not the
  translated label) keeps this language-independent.
"""

from __future__ import annotations

import logging
import os

import dbus

log = logging.getLogger(__name__)

SINGLE_INSTANCE_NAME = "com.pais.handy.SingleInstance"
SINGLE_INSTANCE_PATH = "/com/pais/handy/SingleInstance"
SINGLE_INSTANCE_IFACE = "org.SingleInstance.DBus"

TOGGLE_TRANSCRIPTION = "--toggle-transcription"
TOGGLE_POST_PROCESS = "--toggle-post-process"
CANCEL = "--cancel"

_PROPS = "org.freedesktop.DBus.Properties"
_SNI = "org.kde.StatusNotifierItem"
_DBUSMENU = "com.canonical.dbusmenu"
_TIMEOUT_S = 1.0


class HandyClient:
    def __init__(self, bus: dbus.bus.BusConnection | None = None):
        # A private connection: the client is used from keyhub's worker thread,
        # independently of whatever main loop the keymapper config sets up.
        self._bus = bus or dbus.bus.BusConnection(dbus.bus.BUS_SESSION)
        self._menu: tuple[str, str] | None = None  # (bus name, menu object path)

    def is_running(self) -> bool:
        return bool(self._bus.name_has_owner(SINGLE_INSTANCE_NAME))

    def send(self, flag: str) -> None:
        """Deliver a CLI flag to the running instance, as ``handy <flag>`` would."""
        obj = self._bus.get_object(SINGLE_INSTANCE_NAME, SINGLE_INSTANCE_PATH, introspect=False)
        obj.ExecuteCallback(
            ["handy", flag], os.getcwd(),
            dbus_interface=SINGLE_INSTANCE_IFACE, signature="ass", timeout=_TIMEOUT_S,
        )

    def busy(self) -> bool | None:
        """True while recording/transcribing, False when idle, None if unknown (no tray)."""
        for attempt in range(2):
            try:
                if self._menu is None:
                    self._menu = self._find_menu()
                if self._menu is None:
                    return None
                return self._menu_is_busy(*self._menu)
            except dbus.DBusException as exc:
                # Handy restarted or the tray was rebuilt; look it up again once.
                log.debug("tray lookup failed (attempt %d): %s", attempt + 1, exc)
                self._menu = None
        return None

    def _pid_of(self, name: str) -> int:
        daemon = self._bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus", introspect=False)
        return int(daemon.GetConnectionUnixProcessID(
            name, dbus_interface="org.freedesktop.DBus", timeout=_TIMEOUT_S
        ))

    def _handy_pid(self) -> int | None:
        try:
            return self._pid_of(SINGLE_INSTANCE_NAME)
        except dbus.DBusException:
            return None

    def _find_menu(self) -> tuple[str, str] | None:
        pid = self._handy_pid()
        if pid is None:
            return None
        watcher = self._bus.get_object(
            "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", introspect=False
        )
        items = watcher.Get(
            "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems",
            dbus_interface=_PROPS, timeout=_TIMEOUT_S,
        )
        for item in items:
            name, sep, path = str(item).partition("/")
            path = sep + path if sep else "/StatusNotifierItem"
            try:
                if self._pid_of(name) != pid:
                    continue
                obj = self._bus.get_object(name, path, introspect=False)
                menu = obj.Get(_SNI, "Menu", dbus_interface=_PROPS, timeout=_TIMEOUT_S)
                return name, str(menu)
            except dbus.DBusException:
                continue
        return None

    def _menu_is_busy(self, name: str, menu_path: str) -> bool:
        menu = self._bus.get_object(name, menu_path, introspect=False)
        _revision, (_id, _props, children) = menu.GetLayout(
            0, 1, ["children-display"], dbus_interface=_DBUSMENU, timeout=_TIMEOUT_S
        )
        has_model_submenu = any(
            child[1].get("children-display") == "submenu" for child in children
        )
        return not has_model_submenu
