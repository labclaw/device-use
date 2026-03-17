"""Tests for operator base classes and AccessibilityOperator."""

from __future__ import annotations

import time
from ctypes import c_void_p
from unittest.mock import MagicMock, patch

import pytest

from device_use.operators.base import BaseOperator, ControlLayer, OperatorResult

# ---------------------------------------------------------------------------
# ControlLayer enum
# ---------------------------------------------------------------------------


class TestControlLayer:
    def test_values(self):
        assert ControlLayer.API == 1
        assert ControlLayer.SCRIPT == 2
        assert ControlLayer.A11Y == 3
        assert ControlLayer.CU == 4

    def test_ordering(self):
        assert ControlLayer.API < ControlLayer.SCRIPT < ControlLayer.A11Y < ControlLayer.CU

    def test_names(self):
        assert ControlLayer.API.name == "API"
        assert ControlLayer.A11Y.name == "A11Y"

    def test_is_int(self):
        assert isinstance(ControlLayer.API, int)
        assert ControlLayer.CU + 1 == 5


# ---------------------------------------------------------------------------
# OperatorResult
# ---------------------------------------------------------------------------


class TestOperatorResult:
    def test_creation_defaults(self):
        r = OperatorResult(success=True, layer_used=ControlLayer.API)
        assert r.success is True
        assert r.layer_used == ControlLayer.API
        assert r.output == ""
        assert r.error == ""
        assert r.duration_s == 0.0

    def test_creation_all_fields(self):
        r = OperatorResult(
            success=False,
            layer_used=ControlLayer.CU,
            output="spectrum data",
            error="timeout exceeded",
            duration_s=5.23,
        )
        assert r.success is False
        assert r.layer_used == ControlLayer.CU
        assert r.output == "spectrum data"
        assert r.error == "timeout exceeded"
        assert r.duration_s == 5.23

    def test_repr_success(self):
        r = OperatorResult(success=True, layer_used=ControlLayer.A11Y, duration_s=1.5)
        assert repr(r) == "OperatorResult(OK, A11Y, 1.50s)"

    def test_repr_failure(self):
        r = OperatorResult(success=False, layer_used=ControlLayer.SCRIPT, duration_s=0.1)
        assert repr(r) == "OperatorResult(FAIL, SCRIPT, 0.10s)"

    def test_slots_prevent_new_attrs(self):
        r = OperatorResult(success=True, layer_used=ControlLayer.API)
        with pytest.raises(AttributeError):
            r.extra = "nope"


# ---------------------------------------------------------------------------
# BaseOperator (abstract)
# ---------------------------------------------------------------------------


class TestBaseOperator:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            BaseOperator()

    def test_concrete_subclass(self):
        class FakeOperator(BaseOperator):
            def available_layers(self):
                return [ControlLayer.API]

            async def execute(self, command, *, layer=None, timeout_s=30.0):
                return OperatorResult(success=True, layer_used=ControlLayer.API)

            async def read_state(self):
                return {}

            async def wait_ready(self, timeout_s=10.0):
                return True

        op = FakeOperator()
        assert op.available_layers() == [ControlLayer.API]


# ---------------------------------------------------------------------------
# AccessibilityOperator (mocked ctypes)
# ---------------------------------------------------------------------------


def _make_mock_frameworks():
    """Create mock CF and AX framework objects."""
    cf = MagicMock()
    ax = MagicMock()

    # AXUIElementCreateApplication returns a fake app ref
    ax.AXUIElementCreateApplication.return_value = 0xDEAD

    # CFStringGetTypeID returns a type ID
    cf.CFStringGetTypeID.return_value = 42

    return cf, ax


def _create_operator_with_mocks():
    """Create an AccessibilityOperator with fully mocked frameworks."""
    cf, ax = _make_mock_frameworks()

    with patch("ctypes.cdll") as mock_cdll, patch("ctypes.util.find_library") as mock_find:
        mock_find.side_effect = lambda name: f"/fake/{name}"
        mock_cdll.LoadLibrary.side_effect = [cf, ax]

        from device_use.operators.a11y import AccessibilityOperator

        op = AccessibilityOperator(pid=12345)

    return op, cf, ax


class TestAccessibilityOperatorInit:
    def test_init_stores_pid(self):
        op, cf, ax = _create_operator_with_mocks()
        assert op._pid == 12345

    def test_init_creates_app_ref(self):
        op, cf, ax = _create_operator_with_mocks()
        ax.AXUIElementCreateApplication.assert_called_once_with(12345)
        assert op._app == 0xDEAD

    def test_init_loads_frameworks(self):
        op, cf, ax = _create_operator_with_mocks()
        assert op._cf is cf
        assert op._ax is ax

    def test_is_base_operator_subclass(self):
        op, cf, ax = _create_operator_with_mocks()
        assert isinstance(op, BaseOperator)

    def test_available_layers(self):
        op, cf, ax = _create_operator_with_mocks()
        assert op.available_layers() == [ControlLayer.A11Y]

    async def test_execute_raises_not_implemented(self):
        op, cf, ax = _create_operator_with_mocks()
        with pytest.raises(NotImplementedError, match="click_menu"):
            await op.execute("ft")


class TestAccessibilityOperatorReadState:
    def test_read_state_no_window(self):
        op, cf, ax = _create_operator_with_mocks()
        # AXFocusedWindow fails (err != 0)
        ax.AXUIElementCopyAttributeValue.return_value = -25204
        state = op.read_state_sync()
        assert state["window_title"] is None
        assert state["command_input"] is None
        assert state["status_lines"] == []
        assert state["dataset"] is None

    def test_read_state_with_window(self):
        op, cf, ax = _create_operator_with_mocks()

        # We need to carefully mock the chain of calls.
        # read_state calls: get_window_title, get_command_input, get_status_text
        # Each of those calls get_focused_window which calls _get_attr("AXFocusedWindow")

        # For simplicity, mock the high-level methods
        op.get_window_title = MagicMock(return_value="TopSpin - test_1H")
        op.get_command_input = MagicMock(return_value="ft")
        op.get_status_text = MagicMock(return_value=["dataset: test_1H", "done"])

        state = op.read_state_sync()
        assert state["window_title"] == "TopSpin - test_1H"
        assert state["command_input"] == "ft"
        assert state["status_lines"] == ["dataset: test_1H", "done"]
        assert state["dataset"] == "dataset: test_1H"
        assert state["last_command_status"] == "done"

    def test_read_state_single_status_line(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_window_title = MagicMock(return_value="TopSpin")
        op.get_command_input = MagicMock(return_value=None)
        op.get_status_text = MagicMock(return_value=["processing..."])

        state = op.read_state_sync()
        assert state["dataset"] == "processing..."
        assert state["last_command_status"] is None


class TestAccessibilityOperatorMenus:
    def test_get_menus_no_menubar(self):
        op, cf, ax = _create_operator_with_mocks()
        ax.AXUIElementCopyAttributeValue.return_value = -25204
        assert op.get_menus() == {}

    def test_get_menus_with_items(self):
        op, cf, ax = _create_operator_with_mocks()

        # Mock the menu traversal at high level
        # Since the ctypes mocking is complex, test the logic via method mocking
        op._get_attr = MagicMock()
        menubar_ref = c_void_p(0xBEEF)

        # First call: get AXMenuBar
        op._get_attr.return_value = (0, menubar_ref)

        # Mock _get_children to return menu structure
        file_menu = MagicMock()
        proc_menu = MagicMock()
        apple_menu = MagicMock()

        file_sub = MagicMock()
        proc_sub = MagicMock()

        file_item1 = MagicMock()
        file_item2 = MagicMock()
        proc_item1 = MagicMock()

        def mock_get_children(el):
            if el is menubar_ref:
                return [apple_menu, file_menu, proc_menu]
            if el is file_menu:
                return [file_sub]
            if el is proc_menu:
                return [proc_sub]
            if el is file_sub:
                return [file_item1, file_item2]
            if el is proc_sub:
                return [proc_item1]
            return []

        def mock_get_str(el, attr):
            str_map = {
                (id(apple_menu), "AXTitle"): "Apple",
                (id(file_menu), "AXTitle"): "File",
                (id(proc_menu), "AXTitle"): "Processing",
                (id(file_item1), "AXTitle"): "Open...",
                (id(file_item2), "AXTitle"): "Save",
                (id(proc_item1), "AXTitle"): "Fourier Transform [ft]",
            }
            return str_map.get((id(el), attr))

        op._get_children = mock_get_children
        op._get_str = mock_get_str

        menus = op.get_menus()
        assert "File" in menus
        assert "Processing" in menus
        assert "Apple" not in menus  # Apple menu is skipped
        assert menus["File"] == ["Open...", "Save"]
        assert menus["Processing"] == ["Fourier Transform [ft]"]

    def test_click_menu_no_menubar(self):
        op, cf, ax = _create_operator_with_mocks()
        ax.AXUIElementCopyAttributeValue.return_value = -25204
        assert op.click_menu("File", "Open") is False

    def test_click_menu_item_not_found(self):
        op, cf, ax = _create_operator_with_mocks()
        menubar_ref = c_void_p(0xBEEF)
        op._get_attr = MagicMock(return_value=(0, menubar_ref))
        op._get_children = MagicMock(return_value=[])
        op._get_str = MagicMock(return_value=None)
        assert op.click_menu("NonExistent") is False

    def test_click_menu_success(self):
        op, cf, ax = _create_operator_with_mocks()
        menubar_ref = c_void_p(0xBEEF)
        menu_item = MagicMock()
        submenu = MagicMock()
        target_item = MagicMock()

        op._get_attr = MagicMock(return_value=(0, menubar_ref))

        def mock_get_children(el):
            if el is menubar_ref:
                return [menu_item]
            if el is menu_item:
                return [submenu]
            if el is submenu:
                return [target_item]
            return []

        def mock_get_str(el, attr):
            if el is menu_item and attr == "AXTitle":
                return "Processing"
            if el is submenu and attr == "AXRole":
                return "AXMenu"
            if el is target_item and attr == "AXTitle":
                return "Fourier Transform [ft]"
            return None

        op._get_children = mock_get_children
        op._get_str = mock_get_str

        # AXPress action succeeds
        ax.AXUIElementPerformAction.return_value = 0
        result = op.click_menu("Processing", "Fourier Transform")
        assert result is True

    def test_click_menu_empty_path(self):
        op, cf, ax = _create_operator_with_mocks()
        with pytest.raises(ValueError, match="at least one menu path component"):
            op.click_menu()


class TestAccessibilityOperatorToolbar:
    def test_get_toolbar_buttons_no_window(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_focused_window = MagicMock(return_value=None)
        assert op.get_toolbar_buttons() == []

    def test_get_toolbar_buttons_with_items(self):
        op, cf, ax = _create_operator_with_mocks()
        win = MagicMock()
        scroll_area = MagicMock()
        toolbar = MagicMock()
        btn1 = MagicMock()
        btn2 = MagicMock()
        other_child = MagicMock()

        op.get_focused_window = MagicMock(return_value=win)

        def mock_get_children(el):
            if el is win:
                return [scroll_area, other_child]
            if el is scroll_area:
                return [toolbar]
            if el is toolbar:
                return [btn1, btn2]
            return []

        def mock_get_str(el, attr):
            str_map = {
                (id(scroll_area), "AXRole"): "AXScrollArea",
                (id(other_child), "AXRole"): "AXGroup",
                (id(toolbar), "AXRole"): "AXToolbar",
                (id(btn1), "AXTitle"): "Process",
                (id(btn2), "AXTitle"): None,
                (id(btn2), "AXDescription"): "Save spectrum",
            }
            return str_map.get((id(el), attr))

        op._get_children = mock_get_children
        op._get_str = mock_get_str

        buttons = op.get_toolbar_buttons()
        assert buttons == ["Process", "Save spectrum"]


class TestAccessibilityOperatorWaitForStatus:
    def test_wait_for_status_immediate_match(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_status_text = MagicMock(return_value=["FT completed successfully"])
        assert op.wait_for_status("completed", timeout_s=1.0) is True

    def test_wait_for_status_case_insensitive(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_status_text = MagicMock(return_value=["PROCESSING DONE"])
        assert op.wait_for_status("processing done", timeout_s=1.0) is True

    def test_wait_for_status_timeout(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_status_text = MagicMock(return_value=["still processing..."])
        start = time.monotonic()
        result = op.wait_for_status("completed", timeout_s=0.3, poll_interval=0.05)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed >= 0.3

    def test_wait_for_status_eventual_match(self):
        op, cf, ax = _create_operator_with_mocks()
        call_count = {"n": 0}

        def side_effect():
            call_count["n"] += 1
            if call_count["n"] >= 3:
                return ["done"]
            return ["processing"]

        op.get_status_text = MagicMock(side_effect=side_effect)
        assert op.wait_for_status("done", timeout_s=2.0, poll_interval=0.05) is True


class TestAccessibilityOperatorHelpers:
    def test_get_app_title(self):
        op, cf, ax = _create_operator_with_mocks()
        op._get_str = MagicMock(return_value="TopSpin")
        assert op.get_app_title() == "TopSpin"

    def test_get_focused_window_none(self):
        op, cf, ax = _create_operator_with_mocks()
        op._get_attr = MagicMock(return_value=(-25204, None))
        assert op.get_focused_window() is None

    def test_get_window_title_no_window(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_focused_window = MagicMock(return_value=None)
        assert op.get_window_title() is None

    def test_get_status_text_no_window(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_focused_window = MagicMock(return_value=None)
        assert op.get_status_text() == []

    def test_get_command_input_no_window(self):
        op, cf, ax = _create_operator_with_mocks()
        op.get_focused_window = MagicMock(return_value=None)
        assert op.get_command_input() is None

    def test_get_children_error(self):
        op, cf, ax = _create_operator_with_mocks()
        op._get_attr = MagicMock(return_value=(-1, None))
        assert op._get_children(c_void_p(0x1234)) == []
