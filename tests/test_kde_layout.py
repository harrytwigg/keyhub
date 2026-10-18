import dbus
import pytest

from keyhub import kde_layout

UK = ("gb", "", "English (UK)")
UK_MAC = ("gb", "mac", "English (UK, Macintosh)")
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


def test_pick_index_chooses_the_variant_for_apple_and_another_otherwise():
    layouts = [UK, UK_MAC]
    assert kde_layout.pick_index(layouts, "mac", apple=True) == 1
    assert kde_layout.pick_index(layouts, "mac", apple=False) == 0


def test_pick_index_takes_the_first_match():
    assert kde_layout.pick_index([US, UK, UK_MAC], "mac", apple=False) == 0
    assert kde_layout.pick_index([UK_MAC, UK, US], "mac", apple=False) == 1


def test_pick_index_none_when_the_list_has_no_such_entry():
    assert kde_layout.pick_index([UK], "mac", apple=True) is None
    assert kde_layout.pick_index([UK_MAC], "mac", apple=False) is None


def test_select_switches_to_the_apple_layout_and_back():
    iface = FakeLayouts([UK, UK_MAC])
    kde_layout.select(True, "mac", iface)
    assert iface.set_calls == [1]
    kde_layout.select(False, "mac", iface)
    assert iface.set_calls == [1, 0]


def test_select_does_nothing_when_already_on_the_right_layout():
    iface = FakeLayouts([UK, UK_MAC], current=1)
    kde_layout.select(True, "mac", iface)
    assert iface.set_calls == []


def test_select_leaves_the_layout_alone_without_a_matching_entry(caplog):
    iface = FakeLayouts([UK])
    kde_layout.select(True, "mac", iface)
    assert iface.set_calls == []
    assert "layout list" in caplog.text


def test_select_propagates_dbus_errors_so_the_watcher_retries():
    class Down(FakeLayouts):
        def getLayoutsList(self):
            raise dbus.DBusException("org.kde.keyboard is not running")

    with pytest.raises(dbus.DBusException):
        kde_layout.select(True, "mac", Down([]))
