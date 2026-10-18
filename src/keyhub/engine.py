"""The keyhub daemon: one process, one set of keyboard grabs.

It boots the xwaykeyz keymapper with the vendored Toshy config (the same
steps as ``xwaykeyz -w -c toshy_config.py``) and inserts the dictation layer
in front of the keymapper's transform, so dictation hotkeys are consumed
before Toshy ever remaps them.
"""

from __future__ import annotations

import logging
import sys

from . import apple, config, conflicts, kde_layout, toshy_runtime
from .config import Config
from .passthrough import Passthrough

log = logging.getLogger(__name__)

# systemd's RestartPreventExitStatus: don't restart-loop while another
# keyboard grabber is running; `keyhub doctor` explains what to do.
EXIT_CONFLICT = 3


def _install_event_hook(cfg: Config, passthrough: Passthrough) -> None:
    """Put keyhub's layers in front of the keymapper: dictation first, then the bypass."""
    from xwaykeyz import input as xinput
    from xwaykeyz import transform as xtransform

    layer = None
    if cfg.dictation.enabled:
        from .dictation import DictationLayer
        from .handy import HandyClient

        layer = DictationLayer.from_config(cfg.dictation, HandyClient())
        hotkeys = ", ".join(b.hotkey.text for b in layer.bindings)
        mode = "push-to-talk" if cfg.dictation.push_to_talk else "toggle"
        log.info("dictation hotkeys: %s (%s)", hotkeys, mode)

    transform = xinput.on_event

    def on_event(event, device):
        if layer is not None and layer.filter(event):
            return
        if passthrough.bypass(event):
            xtransform._output.send_event(event)
            return
        transform(event, device)

    xinput.on_event = on_event


def ignored_devices(cfg: Config, toshy_ignored: list[str]) -> list[str]:
    """Devices never to grab: Toshy's, keyhub's built-ins, then the config's.

    The built-ins are always included, not just defaulted, so a config.toml
    written before one was added still ignores it.
    """
    return list(dict.fromkeys([
        *toshy_ignored, *config.DEFAULT_IGNORE_DEVICES, *cfg.keyboard.ignore_devices,
    ]))


def _apply_kbtype_setting(runtime, cfg: Config, passthrough: Passthrough | None = None) -> None:
    kb = cfg.keyboard
    if kb.apple_when_present or kb.apple_layout_variant or kb.passthrough_without_apple:
        _watch_apple_keyboards(runtime, cfg, passthrough or Passthrough())
    if kb.apple_when_present:
        return
    if "override_kbtype" not in cfg.toshy and toshy_runtime.clear_forced_kbtype(runtime):
        log.info("cleared a leftover Apple keyboard type from an earlier run")


def _watch_apple_keyboards(runtime, cfg: Config, passthrough: Passthrough) -> None:
    """Follow whether an Apple keyboard is plugged in, for each setting that cares."""
    kb = cfg.keyboard
    fallback = cfg.toshy.get("override_kbtype", toshy_runtime.DEFAULT_KBTYPE)

    def apply(present: bool) -> None:
        if kb.passthrough_without_apple:
            passthrough.want(not present)
            log.info("Toshy keymaps: %s", "on" if present else "bypassed (plain PC keys)")
        if kb.apple_when_present:
            kbtype = apple.kbtype_for(present, fallback)
            toshy_runtime.sync_prefs(runtime, {"override_kbtype": kbtype})
            log.info("keyboard type: %s", kbtype)
        if kb.apple_layout_variant:
            kde_layout.select(present, kb.apple_layout_variant)

    apple.watch(apply)


def run(cfg: Config) -> None:
    blocking = [c for c in conflicts.check() if c.blocking]
    if blocking:
        for c in blocking:
            log.error("conflict: %s", c.summary)
        log.error("another program is grabbing the keyboard; run `keyhub setup` to fix")
        sys.exit(EXIT_CONFLICT)

    runtime = toshy_runtime.deploy()
    toshy_runtime.sync_prefs(runtime, cfg.toshy)
    passthrough = Passthrough()
    _apply_kbtype_setting(runtime, cfg, passthrough)
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

    _install_event_hook(cfg, passthrough)

    only = config_api._DEVICE_ARGS["only_devices"] or None
    ignore = ignored_devices(cfg, config_api._DEVICE_ARGS["ignore_devices"])
    main_loop(only, True, ignore)
