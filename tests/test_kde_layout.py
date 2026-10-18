import dbus
import pytest

from keyhub import kde_layout

# What KWin's getLayoutsList returns: (layout, display name, description). No variant.
UK = ("gb", "", "English (UK)")
UK_MAC = ("gb", "", "English (UK, Macintosh)")
US = ("us", "", "English (US)")


class FakeLayouts:
    """Stands in for KWin's org.kde.KeyboardLayouts D-Bus interface."""

    def __init__(self, layouts, current=0):
        self.layouts, self.current, self.set_calls = layouts, current, []

    def getLayoutsList(self):
        return self.layouts

    def getLayout(self):
        return self.current

    def setLayout(self, index):
        self.set_calls.append(int(index))
        self.current = int(index)


def kxkbrc(tmp_path, text):
    path = tmp_path / "kxkbrc"
    path.write_text(text)
    return path


def test_configured_variants_lines_up_with_the_layout_list(tmp_path):
    path = kxkbrc(tmp_path, "[Layout]\nDisplayNames=,\nLayoutList=gb,gb\nUse=true\nVariantList=,mac\n")
    assert kde_layout.configured_variants(path) == ["", "mac"]


def test_configured_variants_pads_a_missing_or_short_variant_list(tmp_path):
    assert kde_layout.configured_variants(
        kxkbrc(tmp_path, "[Layout]\nUse=true\nLayoutList=gb,us,de\nVariantList=mac\n")) == ["mac", "", ""]
    assert kde_layout.configured_variants(
        kxkbrc(tmp_path, "[Layout]\nUse=true\nLayoutList=gb,gb\n")) == ["", ""]


def test_configured_variants_empty_without_a_layout_list(tmp_path):
    assert kde_layout.configured_variants(tmp_path / "missing") == []
    assert kde_layout.configured_variants(kxkbrc(tmp_path, "[Other]\nx=1\n")) == []
    assert kde_layout.configured_variants(kxkbrc(tmp_path, "not an ini file")) == []


def test_pick_index_chooses_the_variant_for_apple_and_another_otherwise():
    assert kde_layout.pick_index(["", "mac"], "mac", apple=True) == 1
    assert kde_layout.pick_index(["", "mac"], "mac", apple=False) == 0


def test_pick_index_takes_the_first_match():
    assert kde_layout.pick_index(["", "", "mac"], "mac", apple=False) == 0
    assert kde_layout.pick_index(["mac", "", ""], "mac", apple=False) == 1


def test_pick_index_none_when_the_list_has_no_such_entry():
    assert kde_layout.pick_index([""], "mac", apple=True) is None
    assert kde_layout.pick_index(["mac"], "mac", apple=False) is None


def test_select_switches_to_the_apple_layout_and_back():
    iface = FakeLayouts([UK, UK_MAC])
    kde_layout.select(True, "mac", iface, ["", "mac"])
    assert iface.set_calls == [1]
    kde_layout.select(False, "mac", iface, ["", "mac"])
    assert iface.set_calls == [1, 0]


def test_select_ignores_what_the_display_name_says():
    # A display name of "mac" on the plain layout must not be mistaken for the variant.
    iface = FakeLayouts([("gb", "mac", "English (UK)"), ("gb", "uk", "English (UK, Macintosh)")])
    kde_layout.select(True, "mac", iface, ["", "mac"])
    assert iface.set_calls == [1]


def test_select_does_nothing_when_already_on_the_right_layout():
    iface = FakeLayouts([UK, UK_MAC], current=1)
    kde_layout.select(True, "mac", iface, ["", "mac"])
    assert iface.set_calls == []


def test_select_leaves_the_layout_alone_without_a_matching_entry(caplog):
    iface = FakeLayouts([UK])
    kde_layout.select(True, "mac", iface, [""])
    assert iface.set_calls == []
    assert "layout list" in caplog.text


def test_select_leaves_the_layout_alone_when_kwin_and_kxkbrc_disagree(caplog):
    iface = FakeLayouts([UK])  # KWin knows one layout, kxkbrc lists two
    kde_layout.select(True, "mac", iface, ["", "mac"])
    assert iface.set_calls == []
    assert "leaving the layout alone" in caplog.text


def test_select_propagates_dbus_errors_so_the_watcher_retries():
    class Down(FakeLayouts):
        def getLayoutsList(self):
            raise dbus.DBusException("org.kde.keyboard is not running")

    with pytest.raises(dbus.DBusException):
        kde_layout.select(True, "mac", Down([]), [])


def test_use_false_means_kxkbrc_layouts_are_not_in_effect(tmp_path):
    path = kxkbrc(tmp_path, "[Layout]\nLayoutList=gb,gb\nUse=false\nVariantList=,mac\n")
    assert kde_layout.configured_variants(path) == []


def test_missing_use_means_not_in_effect(tmp_path):
    path = kxkbrc(tmp_path, "[Layout]\nLayoutList=gb,gb\nVariantList=,mac\n")
    assert kde_layout.configured_variants(path) == []


def test_use_true_is_case_and_space_tolerant(tmp_path):
    path = kxkbrc(tmp_path, "[Layout]\nLayoutList=gb,gb\nUse = True \nVariantList=,mac\n")
    assert kde_layout.configured_variants(path) == ["", "mac"]


def test_non_utf8_kxkbrc_is_treated_as_unreadable(tmp_path):
    path = tmp_path / "kxkbrc"
    path.write_bytes(b"[Layout]\nDisplayNames=\xff,\nLayoutList=gb,gb\nUse=true\nVariantList=,mac\n")
    assert kde_layout.configured_variants(path) == []


def test_variant_matching_ignores_case_and_spaces():
    assert kde_layout.pick_index(["", "mac"], " MAC ", apple=True) == 1
    assert kde_layout.pick_index(["", "MAC"], "mac", apple=False) == 0


def test_unplug_keeps_a_non_variant_layout_you_are_already_on():
    # List: us, gb(mac), gb. Sitting on gb (index 2): don't jump to us (index 0).
    assert kde_layout.pick_index(["", "mac", ""], "mac", apple=False, current=2) == 2
    assert kde_layout.pick_index(["", "mac", ""], "mac", apple=False, current=1) == 0


def test_plug_keeps_a_variant_layout_you_are_already_on():
    assert kde_layout.pick_index(["mac", "", "mac"], "mac", apple=True, current=2) == 2


def test_select_does_not_jump_between_equally_good_layouts():
    iface = FakeLayouts([US, UK_MAC, UK], current=2)
    kde_layout.select(False, "mac", iface, ["", "mac", ""])
    assert iface.set_calls == []
