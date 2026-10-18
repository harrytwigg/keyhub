# keyhub

Mac-style keymaps ([Toshy](https://github.com/RedBearAK/toshy)) and push-to-talk
dictation ([Handy](https://github.com/cjpais/Handy)) on Linux, with **one**
process owning the keyboard.

## Why

Toshy and Handy both grab every keyboard exclusively (`EVIOCGRAB`) and re-emit
keys through their own virtual devices. Run both and they stack on top of
each other: whichever starts first wins, hot-plugged keyboards get fought
over, and shortcuts work or don't depending on startup order.

keyhub fixes this by giving the keyboard to a single process:

```
physical keyboards ──grab──▶ keyhub ─┬─ dictation layer ──D-Bus──▶ Handy (speech-to-text only)
                                     │   (eats its hotkeys)
                                     └─ Toshy keymaps (xwaykeyz) ──uinput──▶ apps
```

- **Toshy's keymaps** run unchanged inside keyhub (vendored, pinned to upstream).
- **Handy** keeps doing speech-to-text, but no longer touches the keyboard.
  keyhub watches for your dictation hotkey *before* Toshy remaps anything and
  tells Handy to start or stop over D-Bus.
- **One config file**: `~/.config/keyhub/config.toml`. Dictation hotkeys,
  ignored devices and Toshy preferences all live there. Handy's own hotkey
  settings are no longer used.
- **No competing.** `keyhub setup` disables everything else that grabs the
  keyboard, and `keyhub run` refuses to start while anything still does.

## Install

Requirements: Handy ≥ 0.9 with its tray icon enabled, and Python ≥ 3.11.
Toshy doesn't need to be installed: keyhub ships its keymaps. If it is,
`keyhub setup` imports its preferences and stops it. After that you can
uninstall Toshy, but keep its KWin script (`toshy-dbus-notifyactivewindow`)
and desktop tweaks. keyhub reinstalls the script if it's missing.

```sh
git clone https://github.com/harrytwigg/keyhub && cd keyhub
./install.sh
```

If keyhub's udev rules aren't installed yet, `install.sh` first runs
`scripts/install-system.sh` with sudo. That script lets the `input` group read
keyboards and write `/dev/uinput`, and adds you to that group, so keyhub
doesn't depend on Toshy's own rules. Log out and back in if you weren't
already in `input`.

`install.sh` then creates a venv in `~/.local/share/keyhub/venv`, links `keyhub` into
`~/.local/bin`, and runs `keyhub setup`, which:

1. Writes `~/.config/keyhub/config.toml`, importing your Handy bindings and
   Toshy preferences.
2. Switches Handy's keyboard backend from `handy_keys` (grabs keyboards) to
   `tauri` (doesn't), restarting Handy around the change.
3. Stops Toshy's systemd units, blocks them from starting (a drop-in that
   `keyhub restore` removes), and moves its tray/kickstart
   autostart entries aside, so nothing can restart Toshy's keymapper.
4. Installs, enables and starts `keyhub.service`, a systemd user unit that
   starts with your desktop session (`graphical-session.target`).

Everything it changed is recorded, and `keyhub restore` puts it all back.

## Use

```sh
keyhub doctor                     # is keyhub the only keyboard owner?
journalctl --user -u keyhub -f    # logs
systemctl --user restart keyhub   # after editing config.toml
keyhub restore                    # undo setup, hand the keyboard back to Toshy and Handy
```

### config.toml

```toml
[dictation]
enabled = true
hotkey = "shift_left+z"                  # Handy key names, physical keys
post_process_hotkey = "ctrl+shift+space" # "" to disable
cancel_key = "escape"                    # only intercepted while dictating
push_to_talk = true                      # false = press to start, press to stop

[keyboard]
ignore_devices = ["ydotool virtual device", "ydotoold virtual device"]  # never grab these
apple_when_present = false               # true: Apple keyboard plugged in => Apple type for all

[toshy]
capslock_mode = "caps_is_caps"           # any Toshy preference
```

Hotkeys use the names from Handy's settings (`ctrl`, `shift_left`, `cmd`,
`option`, `space`, `f13`, …) and match the keys you physically press, before
any Toshy remapping. Extra modifiers don't match: `shift_left+z` ignores
Ctrl+Shift+Z.

Toshy picks a keyboard type per device by default: an Apple keyboard gets
the Apple keymap and the laptop's own keyboard the Windows one. With
`apple_when_present = true`, keyhub instead forces the Apple type on every
keyboard while one is plugged in (matched by an `Apple` or `Magic Keyboard`
device name) and hands the choice back to Toshy when it is unplugged. Toshy
reloads live, so nothing restarts. A fixed `override_kbtype` under `[toshy]`
is what comes back after unplugging.

`ydotool virtual device` (ydotool 0.1.x) and `ydotoold virtual device`
(ydotool 1.x) are ignored by default because Handy pastes by
typing Ctrl+V through it. If keyhub grabbed it, Toshy would remap the paste.

## How dictation is driven

Handy only accepts *toggle* commands from outside, so push-to-talk is a
toggle on press and another on release. A blind toggle can go wrong: press
while Handy is still pasting (the press is ignored), release, and the
release starts a recording nobody asked for. keyhub avoids that by checking
whether Handy is busy before every toggle. While Handy is recording or
transcribing, its tray menu replaces the model submenu with a Cancel item,
so keyhub can read that state over D-Bus without depending on the menu's
language.

If Handy isn't running, the hotkeys pass through to your apps like ordinary
keys.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

| Path | What it is |
|---|---|
| `src/keyhub/engine.py` | Boots xwaykeyz with the Toshy config and inserts the dictation layer |
| `src/keyhub/dictation.py` | Hotkey state machine (input thread) and Handy worker thread |
| `src/keyhub/handy.py` | Handy over D-Bus: toggles, cancel, busy state |
| `src/keyhub/hotkeys.py` | Parses Handy-style hotkey strings |
| `src/keyhub/conflicts.py` | Detects, disables and restores competing keyboard grabbers |
| `src/keyhub/toshy_runtime.py` | Deploys the vendored Toshy files, syncs prefs, runs the KWin service |
| `src/keyhub/vendor/toshy/` | Unmodified Toshy runtime; update with `scripts/update-vendor.sh` |

## License

GPL-3.0-or-later. See [NOTICE.md](NOTICE.md) for the bundled and linked
projects.
