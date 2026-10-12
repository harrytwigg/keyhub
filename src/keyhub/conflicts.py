"""Find and fix anything else that wants to own the keyboard.

keyhub only works if it is the *sole* process grabbing keyboards. ``check()``
lists every competitor; ``fix()`` disables the ones keyhub knows how to
(recording what it changed, so ``restore()`` can put everything back);
``keyhub run`` refuses to start while a blocking conflict remains.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import DATA_DIR

HANDY_SETTINGS = Path.home() / ".local/share/com.pais.handy/settings_store.json"
HANDY_GRABBING_BACKEND = "handy_keys"
HANDY_PASSIVE_BACKEND = "tauri"

# toshy-config runs the keymapper itself; the others restart it or duplicate
# the window-context D-Bus name keyhub now provides.
TOSHY_UNITS = [
    "toshy-config.service",
    "toshy-session-monitor.service",
    "toshy-kwin-dbus.service",
    "toshy-cosmic-dbus.service",
    "toshy-wlroots-dbus.service",
]
# The tray and kickstart entries (re)start the units above.
TOSHY_AUTOSTART = ["Toshy_Tray.desktop", "Toshy_Systemd_Service_Kickstart.desktop"]
AUTOSTART_DIR = Path.home() / ".config/autostart"
DISABLED_AUTOSTART_DIR = DATA_DIR / "disabled-autostart"
RESTORE_FILE = DATA_DIR / "restore.json"

# Toshy installs its units into ~/.config/systemd/user, where `systemctl mask`
# can't work (the mask symlink would replace the unit file). A drop-in with an
# always-false condition blocks every start instead, whoever requests it.
SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"
BLOCK_DROPIN = "50-keyhub-blocked.conf"
BLOCK_DROPIN_TEXT = """\
# Written by keyhub: keyhub owns the keyboard, so this unit must not start.
# `keyhub restore` removes this file.
[Unit]
ConditionPathExists=!/
"""

# Executable names of other keymappers that grab input devices.
OTHER_GRABBERS = {
    "xwaykeyz": "xwaykeyz (Toshy's keymapper)",
    "keyszer": "keyszer",
    "xkeysnail": "xkeysnail",
    "kmonad": "kmonad",
    "kanata": "kanata",
    "keyd": "keyd",
    "input-remapper-service": "input-remapper",
}


@dataclass
class Conflict:
    summary: str
    fix: str | None  # what fix() will do, or None if it has to be done by hand
    blocking: bool = True


# ---- probes -----------------------------------------------------------------

def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def _unit_state(unit: str) -> tuple[str, str]:
    enabled = _systemctl("is-enabled", unit).stdout.strip()
    active = _systemctl("is-active", unit).stdout.strip()
    return enabled, active


def _block_dropin(unit: str) -> Path:
    return SYSTEMD_USER_DIR / f"{unit}.d" / BLOCK_DROPIN


def _read_handy_settings() -> dict | None:
    try:
        return json.loads(HANDY_SETTINGS.read_text())
    except (OSError, ValueError):
        return None


def handy_settings() -> dict:
    return (_read_handy_settings() or {}).get("settings", {})


def _handy_pids() -> list[int]:
    out = subprocess.run(["pgrep", "-x", "handy"], capture_output=True, text=True).stdout
    return [int(p) for p in out.split()]


def _running_programs():
    """Yield (pid, program path) for every process, seeing through interpreters."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
        except OSError:
            continue
        program = argv[0]
        if Path(program).name.startswith("python") and len(argv) > 1:
            program = next((a for a in argv[1:] if not a.startswith("-")), program)
        if program:
            yield int(entry.name), program


def check() -> list[Conflict]:
    conflicts = []

    settings = handy_settings()
    if settings.get("keyboard_implementation") == HANDY_GRABBING_BACKEND:
        conflicts.append(Conflict(
            "Handy's keyboard backend (handy_keys) grabs every keyboard",
            f"switch Handy to the '{HANDY_PASSIVE_BACKEND}' backend (restarts Handy)",
        ))
    if settings and not settings.get("show_tray_icon", True):
        conflicts.append(Conflict(
            "Handy's tray icon is off, so keyhub can't see when Handy is busy",
            None, blocking=False,
        ))

    for unit in TOSHY_UNITS:
        enabled, active = _unit_state(unit)
        running = active in ("active", "activating")
        startable = enabled in ("enabled", "enabled-runtime") and not _block_dropin(unit).exists()
        if running or startable:
            conflicts.append(Conflict(
                f"{unit} is {active}/{enabled}", "stop it and block it from starting",
                blocking=running,
            ))

    for name in TOSHY_AUTOSTART:
        if (AUTOSTART_DIR / name).exists():
            conflicts.append(Conflict(
                f"autostart entry {name} restarts Toshy's services",
                "move it aside", blocking=False,
            ))

    for pid, program in _running_programs():
        label = OTHER_GRABBERS.get(Path(program).name)
        if label:
            toshy = "/toshy/" in program
            conflicts.append(Conflict(
                f"{label} is running (pid {pid})",
                "stop it along with Toshy's services" if toshy else None,
            ))
    return conflicts


# ---- fixes ------------------------------------------------------------------

def _load_restore() -> dict:
    try:
        return json.loads(RESTORE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_restore(state: dict) -> None:
    RESTORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESTORE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def _stop_handy() -> bool:
    """Quit Handy and wait for it to exit. Returns whether it was running."""
    pids = _handy_pids()
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
    while _handy_pids() and time.monotonic() < deadline:
        time.sleep(0.2)
    if _handy_pids():
        raise RuntimeError("Handy did not quit; close it from its tray menu and retry")
    return bool(pids)


def _start_handy() -> None:
    handy = shutil.which("handy")
    if handy:
        subprocess.Popen([handy], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def set_handy_backend(backend: str) -> str | None:
    """Set Handy's keyboard backend, restarting Handy around the edit.

    Handy rewrites its settings file while running, so it must be closed first.
    Returns the previous backend.
    """
    data = _read_handy_settings()
    if data is None:
        return None
    previous = data.get("settings", {}).get("keyboard_implementation")
    if previous == backend:
        return previous
    was_running = _stop_handy()
    data = _read_handy_settings()  # re-read: Handy may have saved on exit
    data["settings"]["keyboard_implementation"] = backend
    HANDY_SETTINGS.write_text(json.dumps(data, indent=2))
    if was_running:
        _start_handy()
    return previous


def fix(log=print) -> None:
    state = _load_restore()

    previous = set_handy_backend(HANDY_PASSIVE_BACKEND)
    if previous and previous != HANDY_PASSIVE_BACKEND:
        state.setdefault("handy_keyboard_implementation", previous)
        log(f"Handy: keyboard backend {previous} -> {HANDY_PASSIVE_BACKEND}")

    blocked = []
    for unit in TOSHY_UNITS:
        enabled, active = _unit_state(unit)
        if not enabled or enabled == "not-found" or _block_dropin(unit).exists():
            continue
        if enabled in ("enabled", "enabled-runtime"):
            _systemctl("disable", unit)
            state.setdefault("enabled_units", [])
            if unit not in state["enabled_units"]:
                state["enabled_units"].append(unit)
        dropin = _block_dropin(unit)
        dropin.parent.mkdir(parents=True, exist_ok=True)
        dropin.write_text(BLOCK_DROPIN_TEXT)
        blocked.append((unit, enabled, active))
    if blocked:
        _systemctl("daemon-reload")
    for unit, enabled, active in blocked:
        _systemctl("stop", unit)
        log(f"Toshy: stopped and blocked {unit} (was {active}/{enabled})")

    subprocess.run(["pkill", "-f", "toshy_tray.py"], capture_output=True)
    for name in TOSHY_AUTOSTART:
        src = AUTOSTART_DIR / name
        if src.exists():
            DISABLED_AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(src, DISABLED_AUTOSTART_DIR / name)
            state.setdefault("moved_autostart", [])
            if name not in state["moved_autostart"]:
                state["moved_autostart"].append(name)
            log(f"Toshy: moved autostart entry {name} aside")

    _save_restore(state)


def restore(log=print) -> None:
    """Undo fix(): give the keyboard back to Toshy and Handy."""
    state = _load_restore()

    for name in state.get("moved_autostart", []):
        src = DISABLED_AUTOSTART_DIR / name
        if src.exists():
            shutil.move(src, AUTOSTART_DIR / name)
            log(f"Toshy: restored autostart entry {name}")

    for unit in TOSHY_UNITS:
        dropin = _block_dropin(unit)
        if dropin.exists():
            dropin.unlink()
            if not any(dropin.parent.iterdir()):
                dropin.parent.rmdir()
    _systemctl("daemon-reload")
    for unit in state.get("enabled_units", []):
        _systemctl("enable", "--now", unit)
        log(f"Toshy: re-enabled {unit}")

    backend = state.get("handy_keyboard_implementation")
    if backend:
        set_handy_backend(backend)
        log(f"Handy: keyboard backend back to {backend}")

    RESTORE_FILE.unlink(missing_ok=True)
