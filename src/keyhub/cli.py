"""keyhub command line: run | doctor | setup | restore."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from . import config, conflicts, toshy_runtime
from .hotkeys import HotkeyError, parse

UNIT_NAME = "keyhub.service"
UNIT_PATH = Path.home() / ".config/systemd/user" / UNIT_NAME
TOSHY_PREFS_DB = Path.home() / ".config/toshy" / toshy_runtime.PREFS_DB

UNIT_TEMPLATE = """\
[Unit]
Description=keyhub: one keyboard owner for Toshy keymaps and Handy dictation
After=graphical-session.target
PartOf=graphical-session.target

[Service]
ExecStart={python} -m keyhub run
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3
RestartPreventExitStatus={exit_conflict}

[Install]
WantedBy=graphical-session.target
"""


def import_existing_config() -> config.Config:
    """Build a first config.toml from Handy's bindings and Toshy's preferences."""
    cfg = config.Config()
    handy = conflicts.handy_settings()
    bindings = handy.get("bindings", {})

    def binding(name: str) -> str | None:
        return bindings.get(name, {}).get("current_binding")

    d = cfg.dictation
    d.hotkey = binding("transcribe") or d.hotkey
    d.post_process_hotkey = binding("transcribe_with_post_process") or ""
    d.cancel_key = binding("cancel") or d.cancel_key
    d.push_to_talk = handy.get("push_to_talk", d.push_to_talk)
    cfg.toshy = toshy_runtime.read_prefs(TOSHY_PREFS_DB)
    return cfg


def validate(cfg: config.Config) -> list[str]:
    errors = []
    d = cfg.dictation
    for name in ("hotkey", "post_process_hotkey", "cancel_key"):
        value = getattr(d, name)
        if value or name == "hotkey":
            try:
                parse(value)
            except HotkeyError as exc:
                errors.append(f"[dictation] {name}: {exc}")
    return errors


def cmd_run(args) -> int:
    from . import engine

    cfg = config.load()
    errors = validate(cfg)
    if errors:
        for err in errors:
            logging.error("%s", err)
        return 1
    engine.run(cfg)
    return 0


def cmd_doctor(args) -> int:
    print(f"config: {config.CONFIG_PATH}" + ("" if config.CONFIG_PATH.exists() else " (missing; run `keyhub setup`)"))
    if config.CONFIG_PATH.exists():
        for err in validate(config.load()):
            print(f"  ✗ {err}")
    active = subprocess.run(["systemctl", "--user", "is-active", UNIT_NAME],
                            capture_output=True, text=True).stdout.strip()
    print(f"service: {UNIT_NAME} is {active}")
    if not os.access("/dev/uinput", os.W_OK):
        print("✗ /dev/uinput is not writable; add a udev rule and join the 'input' group (see README)")

    found = conflicts.check()
    if not found:
        print("✓ keyhub is the only program that owns the keyboard")
        return 0
    for c in found:
        mark = "✗" if c.blocking else "!"
        action = f"setup will {c.fix}" if c.fix else "fix by hand"
        print(f"{mark} {c.summary}  ({action})")
    return 1 if any(c.blocking for c in found) else 0


def cmd_setup(args) -> int:
    if config.CONFIG_PATH.exists():
        print(f"Keeping existing {config.CONFIG_PATH}")
    else:
        cfg = import_existing_config()
        config.save(cfg)
        print(f"Wrote {config.CONFIG_PATH} (imported Handy bindings and Toshy preferences)")

    conflicts.fix()

    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    from .engine import EXIT_CONFLICT
    UNIT_PATH.write_text(UNIT_TEMPLATE.format(python=sys.executable, exit_conflict=EXIT_CONFLICT))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", UNIT_NAME], check=True)
    subprocess.run(["systemctl", "--user", "restart", UNIT_NAME], check=True)
    print(f"Started {UNIT_NAME}. Logs: journalctl --user -u keyhub -f")
    print()
    return cmd_doctor(args)


def cmd_restore(args) -> int:
    subprocess.run(["systemctl", "--user", "disable", "--now", UNIT_NAME], capture_output=True)
    conflicts.restore()
    print(f"keyhub stopped; Toshy and Handy own the keyboard again. {config.CONFIG_PATH} was kept.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="keyhub", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="run the keyboard daemon (normally via systemd)")
    sub.add_parser("doctor", help="check that nothing else is grabbing the keyboard")
    sub.add_parser("setup", help="import config, disable competing grabbers, install the service")
    sub.add_parser("restore", help="undo setup and hand the keyboard back to Toshy and Handy")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="keyhub %(levelname)s %(name)s: %(message)s",
    )
    handler = {"run": cmd_run, "doctor": cmd_doctor, "setup": cmd_setup, "restore": cmd_restore}
    return handler[args.command](args)
