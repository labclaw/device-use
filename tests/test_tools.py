"""Tests for external tool integrations (PubChem, ToolUniverse)."""

import pytest

from device_use.tools.base import BaseTool
from device_use.tools.pubchem import PubChemError, PubChemTool
from device_use.tools.tooluniverse import ToolUniverseError, ToolUniverseTool, get_available_tools

# ── BaseTool ─────────────────────────────────────────────────────


class TestBaseTool:
    def test_abstract_methods(self):
        """BaseTool cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTool()


# ── PubChemTool ──────────────────────────────────────────────────


class TestPubChemTool:
    def test_tool_interface(self):
        tool = PubChemTool()
        assert tool.name == "pubchem"
        assert "PubChem" in tool.description or "compound" in tool.description
        assert repr(tool) == "<PubChemTool name='pubchem'>"

    @pytest.mark.network
    def test_lookup_by_name(self):
        tool = PubChemTool()
        result = tool.lookup_by_name("aspirin")
        assert "CID" in result
        assert result["MolecularFormula"] == "C9H8O4"

    @pytest.mark.network
    @pytest.mark.timeout(30)
    def test_lookup_by_formula(self):
        tool = PubChemTool()
        result = tool.lookup_by_formula("C9H8O4")
        assert "CID" in result

    @pytest.mark.network
    def test_get_compound_summary(self):
        tool = PubChemTool()
        summary = tool.get_compound_summary(2244)  # aspirin
        assert "2244" in summary
        assert "C9H8O4" in summary

    @pytest.mark.network
    def test_execute_dispatch_name(self):
        tool = PubChemTool()
        result = tool.execute(name="ethanol")
        assert "CID" in result
        assert result["MolecularFormula"] == "C2H6O"

    def test_execute_no_args(self):
        tool = PubChemTool()
        with pytest.raises(ValueError, match="requires one of"):
            tool.execute()

    @pytest.mark.network
    def test_lookup_nonexistent(self):
        tool = PubChemTool()
        with pytest.raises(PubChemError):
            tool.lookup_by_name("zzz_nonexistent_compound_xyz_12345")


# ── ToolUniverseTool ─────────────────────────────────────────────


class TestToolUniverseTool:
    def test_tool_interface(self):
        tool = ToolUniverseTool()
        assert tool.name == "tooluniverse"
        assert "ToolUniverse" in tool.description or "scientific" in tool.description

    def test_not_connected_initially(self):
        tool = ToolUniverseTool()
        assert tool.connected is False

    def test_available_property(self):
        tool = ToolUniverseTool()
        # Should be bool regardless of installation status
        assert isinstance(tool.available, bool)

    def test_connect_without_package(self):
        """If tooluniverse not installed, connect should raise."""
        from device_use.tools import tooluniverse as tu_mod

        if tu_mod._TU_AVAILABLE:
            pytest.skip("tooluniverse is installed")
        tool = ToolUniverseTool()
        with pytest.raises(ToolUniverseError, match="not installed"):
            tool.connect()

    def test_execute_unknown_action(self):
        tool = ToolUniverseTool()
        # This should raise ValueError for unknown action
        # (not ToolUniverseError for not connected, since action validation is first)
        with pytest.raises((ValueError, ToolUniverseError)):
            tool.execute(action="nonexistent")


# ── Tool Registry ────────────────────────────────────────────────


class TestToolRegistry:
    def test_get_available_tools(self):
        tools = get_available_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 1  # At least PubChem

        # PubChem should always be present
        names = [t.name for t in tools]
        assert "pubchem" in names

        # All tools should be BaseTool instances
        for tool in tools:
            assert isinstance(tool, BaseTool)
