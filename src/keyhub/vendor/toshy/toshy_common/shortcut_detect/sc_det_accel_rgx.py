#!/usr/bin/env python3
"""
toshy_common/shortcut_detect/sc_det_accel_rgx.py

Compiled regex patterns for parsing keyboard shortcut accelerator strings
from desktop environment settings storage.

Patterns are kept in this dedicated module (imported into the consumer
modules) so that pattern editing never happens inside larger modules.
"""
__version__ = '20260831'

import re


# Matches one GTK-style modifier token, e.g. '<Shift>' or '<Primary>'.
# Used with .findall() to extract all modifier tokens from an accelerator
# string like '<Control><Shift>Print'.
_rgx_gtk_mod_token          = re.compile(r'<([A-Za-z0-9]+)>')

# Key names spelled identically in X keysyms, Qt PortableText, and the
# xwaykeyz Key enum: a single letter, a single digit, or F1-F24. These
# pass through the keyname lookups untranslated.
_rgx_keyname_passthrough    = re.compile(r'^(?:[A-Za-z]|[0-9]|F(?:[1-9]|1[0-9]|2[0-4]))$')

# Qt PortableText spelling of the XF86Launch0..F keysyms as stored in
# kglobalshortcutsrc, e.g. 'Launch (9)' or 'Launch (B)'. Group 1 is the
# hex index character.
_rgx_kde_launch_name        = re.compile(r'^Launch \(([0-9A-F])\)$')

# Validates a fully normalized xwaykeyz-style combo string,
# e.g. 'Shift-C-Print' or 'Print'. Used to sanity-check both parser
# output and caller-supplied combo strings.
_rgx_combo_valid            = re.compile(r'^[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*$')

# End of file #
