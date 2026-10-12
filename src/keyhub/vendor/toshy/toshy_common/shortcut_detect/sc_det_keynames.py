#!/usr/bin/env python3
"""
toshy_common/shortcut_detect/sc_det_keynames.py

Desktop-environment key name -> xwaykeyz Key name translation tables and
lookups, shared by every shortcut reader (gsettings/GTK, xfconf, KDE
kglobalshortcutsrc, COSMIC RON).

Why this exists: the readers previously passed unknown key names through
untouched and declared the slot "resolved". A GNOME user with screenshots
bound to a ThinkPad's dedicated key (GTK accelerator 'Launch9') produced
the combo string 'Shift-Launch9', which the keymapper's C() rejected with
KeyError('LAUNCH9') and took the whole config down. Anything not in these
tables (and not a letter, digit, or F1-F24) now returns None so the slot
ends up unresolved instead.

Provenance (derived mechanically, not from memory):
  * keysym -> evdev code: xkeyboard-config 2.41, symbols/inet block
    "evdev", symbols/pc block "pc105", symbols/us block "basic",
    symbols/keypad block "x11", keycodes/evdev (X keycode = evdev + 8).
  * evdev code -> kernel name: linux/include/uapi/linux/input-event-codes.h
  * kernel name -> xwaykeyz name: xwaykeyz/models/key.py Key enum.
  * KDE names: Qt 6 qxkbcommon.cpp (keysym -> Qt::Key) joined with
    qkeysequence.cpp (Qt::Key -> untranslated PortableText string, which
    is what kglobalshortcutsrc stores). Qt 5 shifts the XF86Launch* keys
    by two (XF86Launch9 -> "Launch (B)"); handled per Plasma major.

Naming conventions in the values: they are spelled in the readable
config-file style ('Page_Up', 'BrightnessUp', 'KPEnter'). The keymapper's
combo parser upper-cases the key token before Key[...] lookup, so casing
is cosmetic; tests/test_sc_det_keynames.py verifies every value against
the real Key enum.

GTK/GDK strip a leading 'XF86' from keysym names ('Launch9', 'AudioMute');
COSMIC keeps it. Lookups strip the prefix so both spellings resolve.

Where a keysym maps to several evdev codes, the dedicated kernel code is
used when it is <= 247; the F13-F23 aliases from xkeyboard-config are used
only when the dedicated code is > 247 (e.g. AudioMicMute -> F20 rather
than KEY_MICMUTE = 248). Reason: X keycode = evdev + 8 must fit in a
byte, so codes above 247 are invisible to X11 and XWayland clients. The
EXTENDED section below is entirely above that ceiling: it is correct on
native Wayland and inert under X11.
"""
__version__ = '20260831'

import os

from toshy_common.shortcut_detect.sc_det_accel_rgx import (
    _rgx_kde_launch_name,
    _rgx_keyname_passthrough,
)


# Modifier-only "combos" that keymap builders emit as a bare Key tap
# rather than through C(). validate_combos() must not reject these.
BARE_MODIFIER_KEYNAMES_SET = {'Shift', 'C', 'Alt', 'Super', 'RSuper'}

_XF86_PREFIX_STR = 'XF86'

# Qt spells XF86Launch0..F as "Launch (0)".."Launch (F)". Under Qt 5 the
# index was offset: "Launch (0)" was XF86MyComputer, "Launch (1)" was
# XF86Calculator, "Launch (N>=2)" was XF86Launch{N-2}.
_QT_LAUNCH_INDEX_STR = '0123456789ABCDEF'
_QT5_LAUNCH_SPECIAL_DCT = {'0': 'Computer', '1': 'Calc'}
_DEFAULT_PLASMA_MAJ_VER = 6


# X keysym name (XF86 prefix removed) -> xwaykeyz Key name.
KEYSYM_TO_KEYNAME_DCT = {

    # --- Core keys (symbols/pc, symbols/us; all <= 247) ---
    'Print':                    'Print',
    'Menu':                     'Compose',
    'Page_Up':                  'Page_Up',
    'Page_Down':                'Page_Down',
    'Super_L':                  'Super',
    'Super_R':                  'RSuper',
    'Escape':                   'Esc',
    'minus':                    'Minus',
    'equal':                    'Equal',
    'BackSpace':                'Backspace',
    'Tab':                      'Tab',
    'bracketleft':              'Left_Brace',
    'bracketright':             'Right_Brace',
    'Return':                   'Enter',
    'semicolon':                'Semicolon',
    'apostrophe':               'Apostrophe',
    'grave':                    'Grave',
    'backslash':                'Backslash',
    'comma':                    'Comma',
    'period':                   'Dot',
    'slash':                    'Slash',
    'space':                    'Space',
    'Caps_Lock':                'CapsLock',
    'Num_Lock':                 'NumLock',
    'Scroll_Lock':              'ScrollLock',
    'Katakana':                 'Katakana',
    'Hiragana':                 'Hiragana',
    'Henkan':                   'Henkan',
    'Hiragana_Katakana':        'KatakanaHiragana',
    'Muhenkan':                 'Muhenkan',
    'Linefeed':                 'LineFeed',
    'Home':                     'Home',
    'Up':                       'Up',
    'Prior':                    'Page_Up',
    'Left':                     'Left',
    'Right':                    'Right',
    'End':                      'End',
    'Down':                     'Down',
    'Next':                     'Page_Down',
    'Insert':                   'Insert',
    'Delete':                   'Delete',
    'Pause':                    'Pause',
    'Hangul':                   'Hangeul',
    'Hangul_Hanja':             'Hanja',
    'SunProps':                 'Props',
    'Undo':                     'Undo',
    'SunFront':                 'Front',
    'Find':                     'Find',
    'Help':                     'Help',
    'Redo':                     'Redo',
    'Cancel':                   'Cancel',

    # --- Keypad (symbols/keypad block "x11") ---
    'KP_0':                     'KP0',
    'KP_1':                     'KP1',
    'KP_2':                     'KP2',
    'KP_3':                     'KP3',
    'KP_4':                     'KP4',
    'KP_5':                     'KP5',
    'KP_6':                     'KP6',
    'KP_7':                     'KP7',
    'KP_8':                     'KP8',
    'KP_9':                     'KP9',
    'KP_Insert':                'KP0',
    'KP_End':                   'KP1',
    'KP_Down':                  'KP2',
    'KP_Next':                  'KP3',
    'KP_Page_Down':             'KP3',
    'KP_Left':                  'KP4',
    'KP_Begin':                 'KP5',
    'KP_Right':                 'KP6',
    'KP_Home':                  'KP7',
    'KP_Up':                    'KP8',
    'KP_Prior':                 'KP9',
    'KP_Page_Up':               'KP9',
    'KP_Delete':                'KPDot',
    'KP_Decimal':               'KPDot',
    'KP_Add':                   'KPPlus',
    'KP_Subtract':              'KPMinus',
    'KP_Multiply':              'KPAsterisk',
    'KP_Divide':                'KPSlash',
    'KP_Enter':                 'KPEnter',
    'KP_Equal':                 'KPEqual',

    # --- Media / laptop function keys (symbols/inet "evdev"; all <= 247) ---
    'AudioForward':             'FastForward',
    'AudioLowerVolume':         'VolumeDown',
    'AudioMedia':               'Media',
    'AudioMicMute':             'F20',
    'AudioMute':                'Mute',
    'AudioNext':                'NextSong',
    'AudioPause':               'PauseCD',
    'AudioPlay':                'PlayPause',
    'AudioPreset':              'Sound',
    'AudioPrev':                'PreviousSong',
    'AudioRaiseVolume':         'VolumeUp',
    'AudioRecord':              'Record',
    'AudioRewind':              'Rewind',
    'AudioStop':                'StopCD',
    'Back':                     'Back',
    'Battery':                  'Battery',
    'Bluetooth':                'Bluetooth',
    'BrightnessAuto':           'Brightness_Auto',
    'Calculator':               'Calc',
    'Close':                    'Close',
    'Copy':                     'Copy',
    'Cut':                      'Cut',
    'Display':                  'SwitchVideoMode',
    'DisplayOff':               'Display_Off',
    'Documents':                'Documents',
    'DOS':                      'MSDos',
    'Eject':                    'EjectCD',
    'Explorer':                 'File',
    'Favorites':                'Bookmarks',
    'Finance':                  'Finance',
    'Forward':                  'Forward',
    'Game':                     'Sport',
    'Go':                       'Connect',
    'HomePage':                 'HomePage',
    'KbdBrightnessDown':        'KbdIllumDown',
    'KbdBrightnessUp':          'KbdIllumUp',
    'KbdLightOnOff':            'KbdIllumToggle',
    'Launch1':                  'Prog1',
    'Launch2':                  'Prog2',
    'Launch3':                  'Prog3',
    'Launch4':                  'Prog4',
    'Launch5':                  'F14',
    'Launch6':                  'F15',
    'Launch7':                  'F16',
    'Launch8':                  'F17',
    'Launch9':                  'F18',
    'LaunchA':                  'Scale',
    'LaunchB':                  'Dashboard',
    'Mail':                     'Mail',
    'MailForward':              'ForwardMail',
    'MenuKB':                   'Menu',
    'Messenger':                'Chat',
    'MonBrightnessCycle':       'Brightness_Cycle',
    'MonBrightnessDown':        'BrightnessDown',
    'MonBrightnessUp':          'BrightnessUp',
    'MyComputer':               'Computer',
    'New':                      'New',
    'Next_VMode':               'Video_Next',
    'Open':                     'Open',
    'Paste':                    'Paste',
    'Phone':                    'Phone',
    'PowerOff':                 'Power',
    'Prev_VMode':               'Video_Prev',
    'Reload':                   'Refresh',
    'Reply':                    'Reply',
    'RFKill':                   'RFKill',
    'RotateWindows':            'Direction',
    'Save':                     'Save',
    'ScreenSaver':              'Coffee',
    'ScrollDown':               'ScrollDown',
    'ScrollUp':                 'ScrollUp',
    'Search':                   'Search',
    'Send':                     'Send',
    'Shop':                     'Shop',
    'Sleep':                    'Sleep',
    'Suspend':                  'Suspend',
    'TaskPane':                 'CycleWindows',
    'Tools':                    'Config',
    'TouchpadOff':              'F23',
    'TouchpadOn':               'F22',
    'TouchpadToggle':           'F21',
    'UWB':                      'UWB',
    'WakeUp':                   'WakeUp',
    'WebCam':                   'Camera',
    'WLAN':                     'WLAN',
    'WWAN':                     'WWAN',
    'WWW':                      'WWW',
    'Xfer':                     'Xfer',

    # --- EXTENDED: evdev codes > 247 (Wayland-only; inert under X11/XWayland) ---
    'braille_dot_1':            'Key_Brl_Dot1',
    'braille_dot_2':            'Key_Brl_Dot2',
    'braille_dot_3':            'Key_Brl_Dot3',
    'braille_dot_4':            'Key_Brl_Dot4',
    'braille_dot_5':            'Key_Brl_Dot5',
    'braille_dot_6':            'Key_Brl_Dot6',
    'braille_dot_7':            'Key_Brl_Dot7',
    'braille_dot_8':            'Key_Brl_Dot8',
    'braille_dot_9':            'Key_Brl_Dot9',
    '10ChannelsDown':           'Key_10ChannelsDown',
    '10ChannelsUp':             'Key_10ChannelsUp',
    '3DMode':                   'Key_3D_Mode',
    'Addressbook':              'Key_AddressBook',
    'ALSToggle':                'Key_ALS_Toggle',
    'AppSelect':                'Key_AppSelect',
    'AspectRatio':              'Key_Screen',
    'Assistant':                'Key_Assistant',
    'AttendantOff':             'Key_Attendant_Off',
    'AttendantOn':              'Key_Attendant_On',
    'AttendantToggle':          'Key_Attendant_Toggle',
    'Audio':                    'Key_Audio',
    'AudioDesc':                'Key_Audio_Desc',
    'AudioRandomPlay':          'Key_Shuffle',
    'Break':                    'Key_Break',
    'BrightnessMax':            'Key_Brightness_Max',
    'BrightnessMin':            'Key_Brightness_Min',
    'Buttonconfig':             'Key_ButtonConfig',
    'Calendar':                 'Key_Calendar',
    'CameraDown':               'Key_Camera_Down',
    'CameraFocus':              'Key_Camera_Focus',
    'CameraLeft':               'Key_Camera_Left',
    'CameraRight':              'Key_Camera_Right',
    'CameraUp':                 'Key_Camera_Up',
    'CameraZoomIn':             'Key_Camera_ZoomIn',
    'CameraZoomOut':            'Key_Camera_ZoomOut',
    'ChannelDown':              'Key_ChannelDown',
    'ChannelUp':                'Key_ChannelUp',
    'ContextMenu':              'Key_Context_Menu',
    'ControlPanel':             'Key_ControlPanel',
    'CycleAngle':               'Key_Angle',
    'Data':                     'Key_Data',
    'Database':                 'Key_Database',
    'DisplayToggle':            'Key_DisplayToggle',
    'DVD':                      'Key_DVD',
    'Editor':                   'Key_Editor',
    'Excel':                    'Key_Spreadsheet',
    'FastReverse':              'Key_FastReverse',
    'Fn':                       'Key_Fn',
    'Fn_Esc':                   'Key_Fn_Esc',
    'FrameBack':                'Key_FrameBack',
    'FrameForward':             'Key_FrameForward',
    'FullScreen':               'Key_Zoom',
    'GraphicsEditor':           'Key_GraphicsEditor',
    'Images':                   'Key_Images',
    'Info':                     'Key_Info',
    'Journal':                  'Key_Journal',
    'KbdInputAssistAccept':     'Key_KbdInputAssist_Accept',
    'KbdInputAssistCancel':     'Key_KbdInputAssist_Cancel',
    'KbdInputAssistNext':       'Key_KbdInputAssist_Next',
    'KbdInputAssistNextgroup':  'Key_KbdInputAssist_NextGroup',
    'KbdInputAssistPrev':       'Key_KbdInputAssist_Prev',
    'KbdInputAssistPrevgroup':  'Key_KbdInputAssist_PrevGroup',
    'Keyboard':                 'Key_Keyboard',
    'LeftDown':                 'Key_Left_Down',
    'LeftUp':                   'Key_Left_Up',
    'LightsToggle':             'Key_Lights_Toggle',
    'LogOff':                   'Key_LogOff',
    'Macro1':                   'Key_Macro1',
    'Macro10':                  'Key_Macro10',
    'Macro11':                  'Key_Macro11',
    'Macro12':                  'Key_Macro12',
    'Macro13':                  'Key_Macro13',
    'Macro14':                  'Key_Macro14',
    'Macro15':                  'Key_Macro15',
    'Macro16':                  'Key_Macro16',
    'Macro17':                  'Key_Macro17',
    'Macro18':                  'Key_Macro18',
    'Macro19':                  'Key_Macro19',
    'Macro2':                   'Key_Macro2',
    'Macro20':                  'Key_Macro20',
    'Macro21':                  'Key_Macro21',
    'Macro22':                  'Key_Macro22',
    'Macro23':                  'Key_Macro23',
    'Macro24':                  'Key_Macro24',
    'Macro25':                  'Key_Macro25',
    'Macro26':                  'Key_Macro26',
    'Macro27':                  'Key_Macro27',
    'Macro28':                  'Key_Macro28',
    'Macro29':                  'Key_Macro29',
    'Macro3':                   'Key_Macro3',
    'Macro30':                  'Key_Macro30',
    'Macro4':                   'Key_Macro4',
    'Macro5':                   'Key_Macro5',
    'Macro6':                   'Key_Macro6',
    'Macro7':                   'Key_Macro7',
    'Macro8':                   'Key_Macro8',
    'Macro9':                   'Key_Macro9',
    'MacroPreset1':             'Key_Macro_Preset1',
    'MacroPreset2':             'Key_Macro_Preset2',
    'MacroPreset3':             'Key_Macro_Preset3',
    'MacroPresetCycle':         'Key_Macro_Preset_Cycle',
    'MacroRecordStart':         'Key_Macro_Record_Start',
    'MacroRecordStop':          'Key_Macro_Record_Stop',
    'MediaRepeat':              'Key_Media_Repeat',
    'MediaTopMenu':             'Key_Media_Top_Menu',
    'News':                     'Key_News',
    'NextFavorite':             'Key_Next_Favorite',
    'Numeric0':                 'Key_Numeric_0',
    'Numeric1':                 'Key_Numeric_1',
    'Numeric11':                'Key_Numeric_11',
    'Numeric12':                'Key_Numeric_12',
    'Numeric2':                 'Key_Numeric_2',
    'Numeric3':                 'Key_Numeric_3',
    'Numeric4':                 'Key_Numeric_4',
    'Numeric5':                 'Key_Numeric_5',
    'Numeric6':                 'Key_Numeric_6',
    'Numeric7':                 'Key_Numeric_7',
    'Numeric8':                 'Key_Numeric_8',
    'Numeric9':                 'Key_Numeric_9',
    'NumericA':                 'Key_Numeric_A',
    'NumericB':                 'Key_Numeric_B',
    'NumericC':                 'Key_Numeric_C',
    'NumericD':                 'Key_Numeric_D',
    'NumericPound':             'Key_Numeric_Pound',
    'NumericStar':              'Key_Numeric_Star',
    'OnScreenKeyboard':         'Key_OnScreen_Keyboard',
    'PauseRecord':              'Key_Pause_Record',
    'Presentation':             'Key_Presentation',
    'PrivacyScreenToggle':      'Key_Privacy_Screen_Toggle',
    'RightDown':                'Key_Right_Down',
    'RightUp':                  'Key_Right_Up',
    'RootMenu':                 'Key_Root_Menu',
    'Screensaver':              'Key_ScreenSaver',
    'SelectiveScreenshot':      'Key_Selective_Screenshot',
    'SlowReverse':              'Key_SlowReverse',
    'SpellCheck':               'Key_SpellCheck',
    'StopRecord':               'Key_Stop_Record',
    'Taskmanager':              'Key_TaskManager',
    'Unmute':                   'Key_Unmute',
    'Video':                    'Key_Video',
    'VideoPhone':               'Key_VideoPhone',
    'VOD':                      'Key_VOD',
    'VoiceCommand':             'Key_VoiceCommand',
    'Voicemail':                'Key_VoiceMail',
    'Word':                     'Key_WordProcessor',
    'WPSButton':                'Key_WPS_Button',
    'ZoomIn':                   'Key_ZoomIn',
    'ZoomOut':                  'Key_ZoomOut',
    'ZoomReset':                'Key_ZoomReset',
}


# Qt PortableText key names as stored in kglobalshortcutsrc -> xwaykeyz
# Key name. Only names that differ from (or are not) X keysym names need
# entries; anything not found here falls back to the keysym table, which
# covers identical spellings ('Home', 'F5', 'A') and letters/digits.
# "Launch (X)" is handled separately (version-dependent). Qt 6 maps both
# XF86AudioMedia and XF86MyComputer to 'Launch Media'; the media key wins.
KDE_KEYNAME_TO_KEYNAME_DCT = {
    'Audio Random Play':            'Key_Shuffle',
    'Back':                         'Back',
    'Backspace':                    'Backspace',
    'Battery':                      'Battery',
    'Bluetooth':                    'Bluetooth',
    'Browser':                      'File',
    'Calculator':                   'Calc',
    'Calendar':                     'Key_Calendar',
    'Cancel':                       'Cancel',
    'CapsLock':                     'CapsLock',
    'Close':                        'Close',
    'Copy':                         'Copy',
    'Cut':                          'Cut',
    'Del':                          'Delete',
    'Display':                      'SwitchVideoMode',
    'Documents':                    'Documents',
    'DOS':                          'MSDos',
    'Down':                         'Down',
    'Eject':                        'EjectCD',
    'End':                          'End',
    'Esc':                          'Esc',
    'Favorites':                    'Bookmarks',
    'Finance':                      'Finance',
    'Find':                         'Find',
    'Forward':                      'Forward',
    'Game':                         'Sport',
    'Go':                           'Connect',
    'Hangul':                       'Hangeul',
    'Hangul Hanja':                 'Hanja',
    'Help':                         'Help',
    'Henkan':                       'Henkan',
    'Hiragana':                     'Hiragana',
    'Hiragana Katakana':            'KatakanaHiragana',
    'Home':                         'Home',
    'Home Page':                    'HomePage',
    'Ins':                          'Insert',
    'Katakana':                     'Katakana',
    'Keyboard':                     'Key_Keyboard',
    'Keyboard Brightness Down':     'KbdIllumDown',
    'Keyboard Brightness Up':       'KbdIllumUp',
    'Keyboard Light On/Off':        'KbdIllumToggle',
    'Keyboard Menu':                'Menu',
    'Launch Mail':                  'Mail',
    'Launch Media':                 'Media',
    'Left':                         'Left',
    'Logoff':                       'Key_LogOff',
    'Mail Forward':                 'ForwardMail',
    'Media Fast Forward':           'FastForward',
    'Media Next':                   'NextSong',
    'Media Pause':                  'PauseCD',
    'Media Play':                   'PlayPause',
    'Media Previous':               'PreviousSong',
    'Media Record':                 'Record',
    'Media Rewind':                 'Rewind',
    'Media Stop':                   'StopCD',
    'Messenger':                    'Chat',
    'Microphone Mute':              'F20',
    'Monitor Brightness Down':      'BrightnessDown',
    'Monitor Brightness Up':        'BrightnessUp',
    'Muhenkan':                     'Muhenkan',
    'New':                          'New',
    'News':                         'Key_News',
    'NumLock':                      'NumLock',
    'Open':                         'Open',
    'Paste':                        'Paste',
    'Pause':                        'Pause',
    'PgDown':                       'Page_Down',
    'PgUp':                         'Page_Up',
    'Phone':                        'Phone',
    'Power Off':                    'Power',
    'Redo':                         'Redo',
    'Reload':                       'Refresh',
    'Reply':                        'Reply',
    'Return':                       'Enter',
    'Right':                        'Right',
    'Rotate Windows':               'Direction',
    'Save':                         'Save',
    'Screensaver':                  'Coffee',
    'ScrollLock':                   'ScrollLock',
    'Search':                       'Search',
    'Send':                         'Send',
    'Shop':                         'Shop',
    'Sleep':                        'Sleep',
    'Spreadsheet':                  'Key_Spreadsheet',
    'Suspend':                      'Suspend',
    'Tab':                          'Tab',
    'Task Panel':                   'CycleWindows',
    'Tools':                        'Config',
    'Touchpad Off':                 'F23',
    'Touchpad On':                  'F22',
    'Touchpad Toggle':              'F21',
    'Ultra Wide Band':              'UWB',
    'Undo':                         'Undo',
    'Up':                           'Up',
    'Video':                        'Key_Video',
    'Volume Down':                  'VolumeDown',
    'Volume Mute':                  'Mute',
    'Volume Up':                    'VolumeUp',
    'Wake Up':                      'WakeUp',
    'WebCam':                       'Camera',
    'Wireless':                     'WLAN',
    'Word Processor':               'Key_WordProcessor',
    'WWW':                          'WWW',
    'XFer':                         'Xfer',
    'Zoom In':                      'Key_ZoomIn',
    'Zoom Out':                     'Key_ZoomOut',
}

# Qt writes unshifted punctuation keys as the literal character.
KDE_PUNCT_TO_KEYNAME_DCT = {
    ',':        'Comma',
    '.':        'Dot',
    '/':        'Slash',
    ';':        'Semicolon',
    "'":        'Apostrophe',
    '[':        'Left_Brace',
    ']':        'Right_Brace',
    '\\':       'Backslash',
    '-':        'Minus',
    '=':        'Equal',
    '`':        'Grave',
}


def keyname_from_keysym(keysym_str: str) -> 'str | None':
    """Translate an X keysym name (GTK/GDK style without the XF86 prefix,
    or xkb style with it) to an xwaykeyz Key name. Returns None for
    anything not known to be emittable, so callers leave the slot
    unresolved rather than hand the keymapper a string it will reject."""
    if not keysym_str:
        return None

    name_str = keysym_str.strip()
    if name_str[:len(_XF86_PREFIX_STR)].lower() == _XF86_PREFIX_STR.lower():
        name_str = name_str[len(_XF86_PREFIX_STR):]

    # Letters, digits and F1-F24 are spelled identically in the Key enum.
    if _rgx_keyname_passthrough.match(name_str):
        return name_str

    keyname = KEYSYM_TO_KEYNAME_DCT.get(name_str)
    if keyname is not None:
        return keyname

    # Case-insensitive fallback (COSMIC parses keysym names that way).
    lowered_str = name_str.lower()
    for table_key, table_val in KEYSYM_TO_KEYNAME_DCT.items():
        if table_key.lower() == lowered_str:
            return table_val
    return None


def _effective_plasma_maj_ver(plasma_maj_ver) -> int:
    """Coerce the caller's Plasma major (int or digit string). When absent,
    fall back to KDE_SESSION_VERSION from the session environment, then
    to the current default (6)."""
    if isinstance(plasma_maj_ver, int):
        return plasma_maj_ver
    if isinstance(plasma_maj_ver, str) and plasma_maj_ver.strip().isdigit():
        return int(plasma_maj_ver.strip())

    env_ver_str = os.environ.get('KDE_SESSION_VERSION', '').strip()
    if env_ver_str.isdigit():
        return int(env_ver_str)
    return _DEFAULT_PLASMA_MAJ_VER


def _keyname_from_kde_launch(index_chr: str, plasma_maj_ver: int) -> 'str | None':
    if plasma_maj_ver >= 6:
        return KEYSYM_TO_KEYNAME_DCT.get(f'Launch{index_chr}')

    # Qt 5 numbering.
    special = _QT5_LAUNCH_SPECIAL_DCT.get(index_chr)
    if special is not None:
        return special
    xf86_index = _QT_LAUNCH_INDEX_STR.index(index_chr) - 2
    if xf86_index < 0 or xf86_index >= len(_QT_LAUNCH_INDEX_STR):
        return None
    return KEYSYM_TO_KEYNAME_DCT.get(f'Launch{_QT_LAUNCH_INDEX_STR[xf86_index]}')


def keyname_from_kde_name(name_str: str, plasma_maj_ver=None) -> 'str | None':
    """Translate a Qt PortableText key name from kglobalshortcutsrc (the
    part after the last '+') to an xwaykeyz Key name, or None."""
    if not name_str:
        return None

    name_str = name_str.strip()

    launch_match = _rgx_kde_launch_name.match(name_str)
    if launch_match:
        return _keyname_from_kde_launch(
            launch_match.group(1), _effective_plasma_maj_ver(plasma_maj_ver))

    keyname = KDE_PUNCT_TO_KEYNAME_DCT.get(name_str)
    if keyname is not None:
        return keyname

    keyname = KDE_KEYNAME_TO_KEYNAME_DCT.get(name_str)
    if keyname is not None:
        return keyname

    return keyname_from_keysym(name_str)

# End of file #
