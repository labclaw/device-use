"""Tests for the InstrumentTemplate."""

from __future__ import annotations

import pytest

from device_use.instruments.base import ControlMode
from device_use.instruments.template import InstrumentTemplate


class TestInstrumentTemplate:
    def test_default_mode(self):
        t = InstrumentTemplate()
        assert t.mode == ControlMode.OFFLINE
        assert t.connected is False

    def test_custom_mode(self):
        t = InstrumentTemplate(mode=ControlMode.API)
        assert t.mode == ControlMode.API

    def test_info(self):
        t = InstrumentTemplate()
        info = t.info()
        assert info.name == "MyInstrument"
        assert info.vendor == "Vendor"
        assert ControlMode.OFFLINE in info.supported_modes

    def test_connect_offline(self):
        t = InstrumentTemplate()
        result = t.connect()
        assert result is True
        assert t.connected is True

    def test_connect_api_raises(self):
        t = InstrumentTemplate(mode=ControlMode.API)
        with pytest.raises(NotImplementedError):
            t.connect()

    def test_connect_gui_raises(self):
        t = InstrumentTemplate(mode=ControlMode.GUI)
        with pytest.raises(NotImplementedError):
            t.connect()

    def test_list_datasets(self):
        t = InstrumentTemplate()
        datasets = t.list_datasets()
        assert len(datasets) == 1
        assert datasets[0]["name"] == "sample_1"

    def test_acquire_offline_raises(self):
        t = InstrumentTemplate()
        with pytest.raises(RuntimeError, match="OFFLINE"):
            t.acquire()

    def test_acquire_api_raises(self):
        t = InstrumentTemplate(mode=ControlMode.API)
        with pytest.raises(NotImplementedError):
            t.acquire()

    def test_process_raises(self):
        t = InstrumentTemplate()
        with pytest.raises(NotImplementedError):
            t.process("some_path")
