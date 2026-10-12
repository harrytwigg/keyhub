"""Live end-to-end check of a running keyhub + Handy.

Creates a virtual keyboard (keyhub grabs it like any hot-plugged keyboard),
holds the default Shift+Z hotkey for a second and prints Handy's busy state.
Records ~1 s from the microphone; anything heard may be pasted.

    ~/.local/share/keyhub/venv/bin/python scripts/smoke-test.py [ptt|cancel]
"""

import sys
import time

from evdev import UInput, ecodes as e

from keyhub.handy import HandyClient

caps = {e.EV_KEY: [e.KEY_A, e.KEY_Z, e.KEY_ESC, e.KEY_LEFTSHIFT, e.KEY_SPACE, e.KEY_ENTER,
                   *range(e.KEY_Q, e.KEY_P + 1)]}
ui = UInput(caps, name="keyhub smoke-test keyboard")
client = HandyClient()
time.sleep(3)  # let keyhub notice and grab the new device


def key(code, value):
    ui.write(e.EV_KEY, code, value)
    ui.syn()


def watch(label, seconds):
    seen, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        busy = client.busy()
        if not seen or seen[-1] != busy:
            seen.append(busy)
        time.sleep(0.05)
    print(f"{label}: busy {seen}")


scenario = sys.argv[1] if len(sys.argv) > 1 else "ptt"
print("Handy idle before:", client.busy() is False)
key(e.KEY_LEFTSHIFT, 1)
key(e.KEY_Z, 1)
watch("holding shift+z", 1.0)          # expect [False, True]
if scenario == "cancel":
    key(e.KEY_ESC, 1)
    key(e.KEY_ESC, 0)
    watch("after escape", 0.5)         # expect [True, False]
key(e.KEY_Z, 0)
key(e.KEY_LEFTSHIFT, 0)
watch("after release", 4.0)            # ptt: [True, False]; cancel: [False]
ui.close()
