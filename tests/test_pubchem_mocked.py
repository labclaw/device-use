"""Mocked tests for PubChem tool — no network required."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from device_use.tools.pubchem import (
    PubChemError,
    PubChemTool,
    _extract_cid,
    _extract_compound,
    _fetch_json,
    _get_properties,
)

# ── _fetch_json ──────────────────────────────────────────────────


class TestFetchJson:
    @patch("device_use.tools.pubchem.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"key": "value"}).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _fetch_json("http://example.com")
        assert result == {"key": "value"}

    @patch("device_use.tools.pubchem.urllib.request.urlopen")
    def test_http_error_with_detail(self, mock_urlopen):
        err_body = json.dumps({"Fault": {"Details": [{"Message": "Compound not found"}]}}).encode()
        exc = urllib.error.HTTPError(
            url="http://example.com", code=404, msg="Not Found", hdrs=None, fp=None
        )
        exc.read = MagicMock(return_value=err_body)

        mock_urlopen.return_value.__enter__ = MagicMock(side_effect=exc)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(PubChemError, match="404: Compound not found"):
            _fetch_json("http://example.com")

    @patch("device_use.tools.pubchem.urllib.request.urlopen")
    def test_http_error_without_detail(self, mock_urlopen):
        exc = urllib.error.HTTPError(
            url="http://example.com", code=500, msg="Server Error", hdrs=None, fp=None
        )
        exc.read = MagicMock(side_effect=Exception("can't read"))
        exc.read.side_effect = Exception("can't read")

        mock_urlopen.return_value.__enter__ = MagicMock(side_effect=exc)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(PubChemError, match="PubChem HTTP 500"):
            _fetch_json("http://example.com")

    @patch("device_use.tools.pubchem.urllib.request.urlopen")
    def test_url_error(self, mock_urlopen):
        url_err = urllib.error.URLError("connection refused")
        mock_urlopen.return_value.__enter__ = MagicMock(side_effect=url_err)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(PubChemError, match="connection refused"):
            _fetch_json("http://example.com")

    @patch("device_use.tools.pubchem.urllib.request.urlopen")
    def test_non_json_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"this is not json"
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(PubChemError, match="non-JSON"):
            _fetch_json("http://example.com")


# ── _extract_compound ────────────────────────────────────────────


class TestExtractCompound:
    def test_extracts_from_pc_compounds(self):
        data = {"PC_Compounds": [{"CID": 2244, "prop": "val"}]}
        result = _extract_compound(data)
        assert result["CID"] == 2244

    def test_extracts_from_information_list(self):
        data = {"InformationList": {"Information": [{"CID": 2244, "prop": "val"}]}}
        result = _extract_compound(data)
        assert result["CID"] == 2244

    def test_no_compounds_raises(self):
        with pytest.raises(PubChemError, match="No compound records"):
            _extract_compound({})

    def test_empty_pc_compounds_raises(self):
        with pytest.raises(PubChemError, match="No compound records"):
            _extract_compound({"PC_Compounds": []})


# ── _extract_cid ─────────────────────────────────────────────────


class TestExtractCid:
    def test_from_pc_compounds(self):
        data = {"PC_Compounds": [{"id": {"id": {"cid": 2244}}}]}
        assert _extract_cid(data) == 2244

    def test_from_identifier_list(self):
        data = {"IdentifierList": {"CID": [2244, 2245]}}
        assert _extract_cid(data) == 2244

    def test_missing_cid_raises(self):
        with pytest.raises(PubChemError, match="Could not extract CID"):
            _extract_cid({"PC_Compounds": [{"id": {"id": {}}}]})


# ── _get_properties ──────────────────────────────────────────────


class TestGetProperties:
    @patch("device_use.tools.pubchem._fetch_json")
    def test_success(self, mock_fetch):
        mock_fetch.return_value = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "IUPACName": "aspirin",
                        "MolecularFormula": "C9H8O4",
                    }
                ]
            }
        }
        result = _get_properties(2244)
        assert result["IUPACName"] == "aspirin"

    @patch("device_use.tools.pubchem._fetch_json")
    def test_empty_properties_raises(self, mock_fetch):
        mock_fetch.return_value = {"PropertyTable": {"Properties": []}}
        with pytest.raises(PubChemError, match="No properties"):
            _get_properties(99999)


# ── PubChemTool (mocked) ────────────────────────────────────────


class TestPubChemToolMocked:
    @patch("device_use.tools.pubchem._fetch_json")
    def test_lookup_by_name_mocked(self, mock_fetch):
        # First call: CID extraction
        mock_fetch.side_effect = [
            {"PC_Compounds": [{"id": {"id": {"cid": 2244}}}]},
            {
                "PropertyTable": {
                    "Properties": [
                        {
                            "CID": 2244,
                            "IUPACName": "2-acetoxybenzoic acid",
                            "MolecularFormula": "C9H8O4",
                            "MolecularWeight": 180.16,
                            "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                            "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                        }
                    ]
                }
            },
        ]
        tool = PubChemTool()
        result = tool.lookup_by_name("aspirin")
        assert result["MolecularFormula"] == "C9H8O4"

    @patch("device_use.tools.pubchem._fetch_json")
    def test_lookup_by_formula_mocked(self, mock_fetch):
        mock_fetch.side_effect = [
            {"IdentifierList": {"CID": [2244]}},
            {
                "PropertyTable": {
                    "Properties": [
                        {
                            "CID": 2244,
                            "IUPACName": "aspirin",
                            "MolecularFormula": "C9H8O4",
                        }
                    ]
                }
            },
        ]
        tool = PubChemTool()
        result = tool.lookup_by_formula("C9H8O4")
        assert result["IUPACName"] == "aspirin"

    @patch("device_use.tools.pubchem._fetch_json")
    def test_get_compound_summary_mocked(self, mock_fetch):
        mock_fetch.return_value = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "IUPACName": "aspirin",
                        "MolecularFormula": "C9H8O4",
                        "MolecularWeight": 180.16,
                        "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "InChI": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3",
                        "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                    }
                ]
            }
        }
        tool = PubChemTool()
        summary = tool.get_compound_summary(2244)
        assert "aspirin" in summary
        assert "C9H8O4" in summary
        assert "2244" in summary

    @patch("device_use.tools.pubchem._fetch_json")
    def test_get_compound_summary_missing_fields(self, mock_fetch):
        mock_fetch.return_value = {"PropertyTable": {"Properties": [{"CID": 2244}]}}
        tool = PubChemTool()
        summary = tool.get_compound_summary(2244)
        assert "N/A" in summary

    @patch("device_use.tools.pubchem._fetch_json")
    def test_get_compound_summary_fallback_smiles(self, mock_fetch):
        mock_fetch.return_value = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    }
                ]
            }
        }
        tool = PubChemTool()
        summary = tool.get_compound_summary(2244)
        assert "CC(=O)OC1=CC=CC=C1C(=O)O" in summary

    def test_execute_dispatch_cid(self):
        tool = PubChemTool()
        with patch.object(tool, "get_compound_summary", return_value="summary"):
            result = tool.execute(cid=2244)
            assert result == "summary"

    def test_execute_dispatch_name(self):
        tool = PubChemTool()
        with patch.object(tool, "lookup_by_name", return_value={"CID": 2244}):
            result = tool.execute(name="aspirin")
            assert result["CID"] == 2244

    def test_execute_dispatch_formula(self):
        tool = PubChemTool()
        with patch.object(tool, "lookup_by_formula", return_value={"CID": 2244}):
            result = tool.execute(formula="C9H8O4")
            assert result["CID"] == 2244
