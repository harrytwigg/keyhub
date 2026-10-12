#!/usr/bin/env python3
"""
toshy_common/shortcut_detect/sc_det_result.py

Shared result model for native shortcut detection: per-slot status and
source constants, the SlotResult container, and the generic resolution
tiering (live settings over static defaults, with explicitly-disabled
shortcuts respected rather than falling through).
"""
__version__ = '20260831'

from toshy_common.logger import debug, error
from toshy_common.shortcut_detect.sc_det_keynames import BARE_MODIFIER_KEYNAMES_SET


# Per-slot resolution status values.
STATUS_RESOLVED             = 'resolved'      # combo available for emission
STATUS_DISABLED             = 'disabled'      # user explicitly disabled native shortcut
STATUS_UNRESOLVED           = 'unresolved'    # no binding known; slot stays unmapped

# Where a resolved combo came from (for logging/diagnostics).
SOURCE_USER_OVERRIDE        = 'user_override'
SOURCE_LIVE_SETTINGS        = 'live_settings'
SOURCE_DEFAULTS_TABLE       = 'defaults_table'
SOURCE_GENERIC_CONVENTION   = 'generic_convention'


class SlotResult:
    """Resolution result for one shortcut slot."""

    def __init__(self, status: str, combo: 'str | None' = None,
                    source: str = '', raw: str = '', note: str = ''):
        self.status     = status
        self.combo      = combo
        self.source     = source
        self.raw        = raw
        self.note       = note

    def __repr__(self):
        return (f'SlotResult(status={self.status!r}, combo={self.combo!r}, '
                f'source={self.source!r}, raw={self.raw!r}, note={self.note!r})')


def log_resolution(prefix_str: str, domain_label_str: str, results_dct: dict,
                    live_dct: dict, table_source: str):
    """Standard resolution logging for any detection consumer: a summary
    counts line plus per-slot SlotResult detail, always emitted under the
    'DT' logging context so consumers cannot drift from the convention.

    prefix_str: the caller's message prefix (e.g. 'SSHOT').
    domain_label_str: human wording for the summary line, e.g.
    "Screenshot shortcuts for 'kde'"."""
    resolved_cnt    = sum(1 for res in results_dct.values() if res.status == STATUS_RESOLVED)
    disabled_cnt    = sum(1 for res in results_dct.values() if res.status == STATUS_DISABLED)
    unresolved_cnt  = sum(1 for res in results_dct.values() if res.status == STATUS_UNRESOLVED)

    live_note = 'live settings read OK' if live_dct else f'no live settings; using {table_source}'
    debug(f'{prefix_str}: {domain_label_str}: '
            f'{resolved_cnt} resolved, {disabled_cnt} disabled, '
            f'{unresolved_cnt} unresolved ({live_note})', ctx='DT')

    for slot_name, result in results_dct.items():
        debug(f'{prefix_str}:   {slot_name}: {result!r}', ctx='DT')


def validate_combos(results_dct: dict, combo_fn, prefix_str: str) -> dict:
    """Run every resolved combo through the keymapper's own combo parser
    (the config's C) and downgrade any it rejects to STATUS_UNRESOLVED,
    loudly. This is the authoritative membership check against the Key
    enum, placed in the one layer that has access to it via injection
    (toshy_common never imports xwaykeyz). It also covers combos that
    never passed through a reader: defaults tables and user overrides.

    Modifier-only combos ('Super') are skipped: builders emit those as a
    bare Key tap, and C() legitimately rejects them.

    Mutates and returns results_dct."""
    for slot_name, result in results_dct.items():
        if result.status != STATUS_RESOLVED or not result.combo:
            continue
        if result.combo in BARE_MODIFIER_KEYNAMES_SET:
            continue
        try:
            combo_fn(result.combo)
        except (KeyError, ValueError) as exc:
            error(f'{prefix_str}: Keymapper rejected combo {result.combo!r} for slot '
                    f"'{slot_name}' ({type(exc).__name__}: {exc}); slot downgraded "
                    'to unresolved. Please report this so the key name table '
                    'can be extended.', ctx='DT')
            results_dct[slot_name] = SlotResult(
                STATUS_UNRESOLVED, source=result.source, raw=result.raw,
                note=f'combo {result.combo!r} rejected by keymapper')
    return results_dct


def resolve_slot_tiers(slot_names, live_dct: dict, table_dct: dict,
                        table_source: str) -> dict:
    """Resolve every slot through the standard tiers.

    live_dct maps slot -> (status, combo, raw, note) from a reader; slots
    present there win, including explicitly-disabled ones (a successful
    read of "disabled" must NOT fall through to defaults). Slots absent
    from live_dct fall to table_dct (slot -> combo). Anything else is
    unresolved. Returns slot -> SlotResult."""
    results_dct = {}
    for slot_name in slot_names:

        if slot_name in live_dct:
            status, combo_str, raw_str, note_str = live_dct[slot_name]
            results_dct[slot_name] = SlotResult(
                status, combo=combo_str, source=SOURCE_LIVE_SETTINGS,
                raw=raw_str, note=note_str)
            continue

        table_combo = table_dct.get(slot_name)
        if table_combo is not None:
            results_dct[slot_name] = SlotResult(
                STATUS_RESOLVED, combo=table_combo, source=table_source)
            continue

        results_dct[slot_name] = SlotResult(STATUS_UNRESOLVED)

    return results_dct

# End of file #
