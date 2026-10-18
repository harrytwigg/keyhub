"""Run the vendored Toshy keymaps: deploy them, apply preferences, start helpers."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import dbus

from .config import DATA_DIR

log = logging.getLogger(__name__)

VENDOR_DIR = Path(__file__).parent / "vendor" / "toshy"
RUNTIME_DIR = DATA_DIR / "toshy"
PREFS_DB = "toshy_user_preferences.sqlite"
KWIN_DBUS_NAME = "org.toshy.Plasma"
KICKSTART_SCRIPT = "toshy-kwin-script-kickstart.sh"
DEFAULT_KBTYPE = "Auto-Adapt"  # Toshy's "no override": identify each keyboard on its own


def deploy() -> Path:
    """Copy the vendored Toshy files somewhere writable.

    Toshy keeps its preferences database next to ``toshy_config.py``, so the
    config can't run from inside the installed package. The copy is refreshed
    on every start (it's ~1 MB) and the preferences database is preserved.
    """
    shutil.copytree(
        VENDOR_DIR, RUNTIME_DIR, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.sqlite"),
    )
    return RUNTIME_DIR


def read_prefs(db_path: Path) -> dict[str, str]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as db:
        try:
            return dict(db.execute("SELECT name, value FROM config_preferences"))
        except sqlite3.OperationalError:
            return {}


def sync_prefs(runtime_dir: Path, prefs: dict[str, str]) -> None:
    """Write keyhub's [toshy] settings into the database Toshy's config reads."""
    if not prefs:
        return
    with sqlite3.connect(runtime_dir / PREFS_DB) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS config_preferences (name TEXT PRIMARY KEY, value TEXT)"
        )
        db.executemany(
            "INSERT INTO config_preferences (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            prefs.items(),
        )


def clear_forced_kbtype(runtime_dir: Path, keep: str = "Apple") -> bool:
    """Drop a leftover ``override_kbtype = keep`` from the preferences database.

    The database outlives runs, so an override written while an Apple keyboard
    was plugged in would otherwise keep forcing that type on every keyboard
    once the feature is switched off. Returns whether it reset the value.
    """
    if read_prefs(runtime_dir / PREFS_DB).get("override_kbtype") != keep:
        return False
    sync_prefs(runtime_dir, {"override_kbtype": DEFAULT_KBTYPE})
    return True


def needs_kwin_service() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return "KDE" in desktop.split(":") and os.environ.get("XDG_SESSION_TYPE") == "wayland"


def _python_env(runtime_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(runtime_dir), env.get("PYTHONPATH")]))
    return env


def start_kwin_service(runtime_dir: Path) -> None:
    """Run Toshy's KWin window-context service as a supervised child process.

    On KDE Wayland the keymapper can only learn the focused app through this
    service, which a KWin script notifies of focus changes. It never touches
    input devices.
    """
    service_dir = runtime_dir / "kwin-dbus-service"
    env = _python_env(runtime_dir)

    def setup_kwin_script():
        # Installs/enables the KWin script if needed (Toshy does the same at start).
        subprocess.run(
            [sys.executable, str(service_dir / "toshy_kwin_script_setup.py")],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # The setup looks for this under ~/.config/toshy, which may not exist,
        # so run keyhub's copy. Its brief dialog makes KWin report the focused
        # window, so app-specific keymaps work before the first window switch.
        subprocess.Popen(
            ["bash", str(runtime_dir / "scripts" / KICKSTART_SCRIPT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    threading.Thread(target=setup_kwin_script, name="keyhub-kwin-setup", daemon=True).start()

    def supervise():
        while True:
            proc = subprocess.Popen(
                [sys.executable, "-u", str(service_dir / "toshy_kwin_dbus_service.py")], env=env,
            )
            code = proc.wait()
            log.warning("KWin window-context service exited (%s); restarting", code)
            time.sleep(2)

    threading.Thread(target=supervise, name="keyhub-kwin", daemon=True).start()
    _wait_for_bus_name(KWIN_DBUS_NAME, timeout=10)


def _wait_for_bus_name(name: str, timeout: float) -> None:
    bus = dbus.bus.BusConnection(dbus.bus.BUS_SESSION)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bus.name_has_owner(name):
            return
        time.sleep(0.1)
    log.warning("%s did not appear on D-Bus; app-specific keymaps may not work", name)
