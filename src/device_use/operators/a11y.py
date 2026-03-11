"""macOS Accessibility API operator for scientific software.

Uses the AX (Accessibility) API to:
  - Read UI element trees (menus, buttons, text fields, status)
  - Click menu items and buttons by name
  - Read/write text fields (command input)
  - Monitor status text for command completion

This is Layer 3 (A11y) in the operator hierarchy — faster than
Computer Use (L4) but slower than API (L1) or Script (L2).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import time
from contextlib import contextmanager
from ctypes import POINTER, byref, c_int32, c_uint32, c_void_p
from typing import Any

from device_use.operators.base import BaseOperator, ControlLayer, OperatorResult


class AccessibilityOperator(BaseOperator):
    """Read and control macOS applications via the Accessibility API."""

    def __init__(self, pid: int):
        self._pid = pid
        self._load_frameworks()
        self._app = self._ax.AXUIElementCreateApplication(pid)

    # ------------------------------------------------------------------
    # BaseOperator abstract methods
    # ------------------------------------------------------------------
    def available_layers(self) -> list[ControlLayer]:
        """Return control layers this operator supports."""
        return [ControlLayer.A11Y]

    async def execute(
        self,
        command: str,
        *,
        layer: ControlLayer | None = None,
        timeout_s: float = 30.0,
    ) -> OperatorResult:
        """Execute a command. Use specific methods like click_menu() instead."""
        raise NotImplementedError(
            "Use specific methods like click_menu(), read_state(), "
            "or wait_for_status() for AccessibilityOperator."
        )

    async def read_state(self) -> dict[str, Any]:
        """Read comprehensive application state (async wrapper)."""
        return self.read_state_sync()

    async def wait_ready(self, timeout_s: float = 10.0) -> bool:
        """Wait until the application is ready for the next command."""
        return self.wait_for_status("done", timeout_s=timeout_s)

    # ------------------------------------------------------------------
    # Framework loading
    # ------------------------------------------------------------------
    def _load_frameworks(self) -> None:
        self._cf = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("CoreFoundation")
        )
        self._ax = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("ApplicationServices")
        )

        # AX functions
        self._ax.AXUIElementCreateApplication.restype = c_void_p
        self._ax.AXUIElementCreateApplication.argtypes = [c_int32]
        self._ax.AXUIElementCopyAttributeValue.restype = c_int32
        self._ax.AXUIElementCopyAttributeValue.argtypes = [
            c_void_p, c_void_p, POINTER(c_void_p),
        ]
        self._ax.AXUIElementPerformAction.restype = c_int32
        self._ax.AXUIElementPerformAction.argtypes = [c_void_p, c_void_p]
        self._ax.AXUIElementSetAttributeValue.restype = c_int32
        self._ax.AXUIElementSetAttributeValue.argtypes = [
            c_void_p, c_void_p, c_void_p,
        ]

        # CF functions
        self._cf.CFStringCreateWithCString.restype = c_void_p
        self._cf.CFStringCreateWithCString.argtypes = [
            c_void_p, ctypes.c_char_p, c_uint32,
        ]
        self._cf.CFStringGetCString.restype = ctypes.c_bool
        self._cf.CFStringGetCString.argtypes = [
            c_void_p, ctypes.c_char_p, ctypes.c_long, c_uint32,
        ]
        self._cf.CFGetTypeID.restype = ctypes.c_ulong
        self._cf.CFGetTypeID.argtypes = [c_void_p]
        self._cf.CFStringGetTypeID.restype = ctypes.c_ulong
        self._cf.CFArrayGetCount.restype = ctypes.c_long
        self._cf.CFArrayGetCount.argtypes = [c_void_p]
        self._cf.CFArrayGetValueAtIndex.restype = c_void_p
        self._cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, ctypes.c_long]

        self._kCFStringEncodingUTF8 = 0x08000100
        self._STRING_TYPE_ID = self._cf.CFStringGetTypeID()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _cfstr(self, s: str) -> c_void_p:
        return self._cf.CFStringCreateWithCString(
            None, s.encode("utf-8"), self._kCFStringEncodingUTF8
        )

    @contextmanager
    def _temp_cfstr(self, s: str):
        """Create a CFString and release it when done."""
        ref = self._cfstr(s)
        try:
            yield ref
        finally:
            if ref:
                self._cf.CFRelease(ref)

    def _to_py(self, ref: c_void_p) -> str | None:
        if not ref:
            return None
        if self._cf.CFGetTypeID(ref) != self._STRING_TYPE_ID:
            return None
        buf = ctypes.create_string_buffer(4096)
        if self._cf.CFStringGetCString(
            ref, buf, 4096, self._kCFStringEncodingUTF8
        ):
            return buf.value.decode("utf-8")
        return None

    def _get_attr(self, el: c_void_p, name: str) -> tuple[int, c_void_p]:
        val = c_void_p()
        with self._temp_cfstr(name) as cf_name:
            err = self._ax.AXUIElementCopyAttributeValue(
                el, cf_name, byref(val)
            )
        return err, val.value

    def _get_str(self, el: c_void_p, name: str) -> str | None:
        err, val = self._get_attr(el, name)
        return self._to_py(val) if err == 0 else None

    def _get_children(self, el: c_void_p) -> list[c_void_p]:
        err, ch = self._get_attr(el, "AXChildren")
        if err != 0 or not ch:
            return []
        count = self._cf.CFArrayGetCount(ch)
        return [self._cf.CFArrayGetValueAtIndex(ch, i) for i in range(count)]

    # ------------------------------------------------------------------
    # Public API: Read state
    # ------------------------------------------------------------------
    def get_app_title(self) -> str | None:
        """Get the application title."""
        return self._get_str(self._app, "AXTitle")

    def get_focused_window(self) -> c_void_p | None:
        """Get the focused window element."""
        err, win = self._get_attr(self._app, "AXFocusedWindow")
        return win if err == 0 else None

    def get_window_title(self) -> str | None:
        """Get the focused window title."""
        win = self.get_focused_window()
        return self._get_str(win, "AXTitle") if win else None

    def get_status_text(self) -> list[str]:
        """Read all visible static text (status lines, labels)."""
        win = self.get_focused_window()
        if not win:
            return []
        texts = []
        for child in self._get_children(win):
            role = self._get_str(child, "AXRole")
            if role == "AXStaticText":
                val = self._get_str(child, "AXValue")
                if val:
                    texts.append(val)
        return texts

    def get_command_input(self) -> str | None:
        """Read the command input field value."""
        win = self.get_focused_window()
        if not win:
            return None
        for child in self._get_children(win):
            role = self._get_str(child, "AXRole")
            if role == "AXTextField":
                return self._get_str(child, "AXValue")
        return None

    def read_state_sync(self) -> dict[str, Any]:
        """Read comprehensive application state (synchronous)."""
        texts = self.get_status_text()
        return {
            "window_title": self.get_window_title(),
            "command_input": self.get_command_input(),
            "status_lines": texts,
            "dataset": texts[0] if texts else None,
            "last_command_status": texts[1] if len(texts) > 1 else None,
        }

    # ------------------------------------------------------------------
    # Public API: Menu operations
    # ------------------------------------------------------------------
    def get_menus(self) -> dict[str, list[str]]:
        """Get all menu items grouped by menu name."""
        err, menubar = self._get_attr(self._app, "AXMenuBar")
        if err != 0 or not menubar:
            return {}
        result = {}
        for menu in self._get_children(menubar):
            title = self._get_str(menu, "AXTitle")
            if not title or title == "Apple":
                continue
            items = []
            for sub in self._get_children(menu):
                for item in self._get_children(sub):
                    t = self._get_str(item, "AXTitle")
                    if t:
                        items.append(t)
            result[title] = items
        return result

    def click_menu(self, *path: str) -> bool:
        """Click a menu item by path. E.g. click_menu("Processing", "Fourier Transform [ft]")."""
        err, menubar = self._get_attr(self._app, "AXMenuBar")
        if err != 0 or not menubar:
            return False

        current_children = self._get_children(menubar)
        for i, name in enumerate(path):
            match = self._find_menu_match(current_children, name)
            if match is None:
                return False
            if i == len(path) - 1:
                # Last item — click it
                with self._temp_cfstr("AXPress") as cf_press:
                    err = self._ax.AXUIElementPerformAction(match, cf_press)
                return err == 0
            else:
                # Intermediate menu — descend
                current_children = self._get_children(match)
                # Flatten: menus have one submenu child containing items
                if current_children:
                    expanded = []
                    for c in current_children:
                        r = self._get_str(c, "AXRole")
                        if r in ("AXMenu", "AXList"):
                            expanded.extend(self._get_children(c))
                        else:
                            expanded.append(c)
                    current_children = expanded
        return False

    def _find_menu_match(
        self, children: list[c_void_p], name: str
    ) -> c_void_p | None:
        """Find a menu child by title — exact match first, then substring."""
        name_lower = name.lower()
        substring_match = None
        for child in children:
            title = self._get_str(child, "AXTitle")
            if not title:
                continue
            if title.lower() == name_lower:
                return child  # Exact match — return immediately
            if substring_match is None and name_lower in title.lower():
                substring_match = child
        return substring_match

    # ------------------------------------------------------------------
    # Public API: Toolbar
    # ------------------------------------------------------------------
    def get_toolbar_buttons(self) -> list[str]:
        """Get all toolbar button titles/descriptions."""
        win = self.get_focused_window()
        if not win:
            return []
        buttons = []
        for child in self._get_children(win):
            role = self._get_str(child, "AXRole")
            if role == "AXScrollArea":
                for sub in self._get_children(child):
                    if self._get_str(sub, "AXRole") == "AXToolbar":
                        for btn in self._get_children(sub):
                            t = self._get_str(btn, "AXTitle") or self._get_str(
                                btn, "AXDescription"
                            )
                            if t:
                                buttons.append(t)
        return buttons

    # ------------------------------------------------------------------
    # Public API: Wait for command completion
    # ------------------------------------------------------------------
    def wait_for_status(
        self,
        contains: str,
        timeout_s: float = 30.0,
        poll_interval: float = 0.3,
    ) -> bool:
        """Poll status text until it contains the expected string."""
        target = contains.lower()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if any(target in t.lower() for t in self.get_status_text()):
                return True
            time.sleep(poll_interval)
        return False
