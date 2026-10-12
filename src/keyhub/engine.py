"""The keyhub daemon: one process, one set of keyboard grabs.

It boots the xwaykeyz keymapper with the vendored Toshy config (the same
steps as ``xwaykeyz -w -c toshy_config.py``) and inserts the dictation layer
in front of the keymapper's transform, so dictation hotkeys are consumed
before Toshy ever remaps them.
"""

from __future__ import annotations

import logging
import sys

from . import conflicts, toshy_runtime
from .config import Config

log = logging.getLogger(__name__)

# systemd's RestartPreventExitStatus: don't restart-loop while another
# keyboard grabber is running; `keyhub doctor` explains what to do.
EXIT_CONFLICT = 3


def _install_dictation(cfg: Config) -> None:
    from xwaykeyz import input as xinput

    from .dictation import DictationLayer
    from .handy import HandyClient

    layer = DictationLayer.from_config(cfg.dictation, HandyClient())
    transform = xinput.on_event

    def on_event(event, device):
        if not layer.filter(event):
            transform(event, device)

    xinput.on_event = on_event
    hotkeys = ", ".join(b.hotkey.text for b in layer.bindings)
    mode = "push-to-talk" if cfg.dictation.push_to_talk else "toggle"
    log.info("dictation hotkeys: %s (%s)", hotkeys, mode)


def run(cfg: Config) -> None:
    blocking = [c for c in conflicts.check() if c.blocking]
    if blocking:
        for c in blocking:
            log.error("conflict: %s", c.summary)
        log.error("another program is grabbing the keyboard; run `keyhub setup` to fix")
        sys.exit(EXIT_CONFLICT)

    runtime = toshy_runtime.deploy()
    toshy_runtime.sync_prefs(runtime, cfg.toshy)
    if toshy_runtime.needs_kwin_service():
        toshy_runtime.start_kwin_service(runtime)

    from xwaykeyz import cli as xcli
    from xwaykeyz import config_api
    from xwaykeyz.input import main_loop
    from xwaykeyz.lib import logger as xlogger

    xlogger.VERBOSE = cfg.verbose
    if not xcli.uinput_device_exists():
        log.error("/dev/uinput does not exist; check your kernel configuration")
        sys.exit(1)
    if not xcli.has_access_to_uinput():
        log.error("cannot open /dev/uinput for writing; check its permissions")
        sys.exit(1)

    try:
        xcli.eval_config(str(runtime / "toshy_config.py"))
    except BaseException:
        xcli.print_config_traceback()
        sys.exit(1)

    if cfg.dictation.enabled:
        _install_dictation(cfg)

    only = config_api._DEVICE_ARGS["only_devices"] or None
    ignore = [*config_api._DEVICE_ARGS["ignore_devices"], *cfg.keyboard.ignore_devices]
    main_loop(only, True, ignore)
