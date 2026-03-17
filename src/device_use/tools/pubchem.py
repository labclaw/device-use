"""PubChem compound lookup tool — wraps PUG REST.

Part of the ToolUniverse / external-tools integration.  The Cloud Brain
calls this after identifying a compound from NMR data to retrieve
authoritative metadata (CID, IUPAC name, molecular weight, SMILES, InChI).

PUG REST docs: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from device_use.tools.base import BaseTool

logger = logging.getLogger(__name__)

_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Properties we pull from every compound record.
_DESIRED_PROPERTIES = (
    "IUPACName",
    "MolecularFormula",
    "MolecularWeight",
    "CanonicalSMILES",
    "IsomericSMILES",
    "InChI",
    "InChIKey",
)

# Seconds to wait for a PUG REST response before giving up.
# The fastformula endpoint can be slow; callers may override per-request.
_REQUEST_TIMEOUT = 30


class PubChemError(Exception):
    """Raised when a PubChem API call fails."""


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _fetch_json(url: str) -> dict:
    """GET *url* and return the parsed JSON body.

    Raises:
        PubChemError: on HTTP errors or unparseable responses.
    """
    logger.debug("PubChem request: %s", url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        # Try to extract PubChem's JSON error message.
        detail = ""
        try:
            err_body = exc.read()
            err_json = json.loads(err_body)
            fault = err_json.get("Fault", {})
            detail = fault.get("Details", [{}])[0].get("Message", "")
        except Exception:  # noqa: BLE001
            pass
        msg = f"PubChem HTTP {exc.code}"
        if detail:
            msg += f": {detail}"
        raise PubChemError(msg) from exc
    except urllib.error.URLError as exc:
        raise PubChemError(f"PubChem connection error: {exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise PubChemError("PubChem returned non-JSON response") from exc


def _extract_compound(data: dict) -> dict:
    """Pull the first compound record out of a PUG REST response."""
    compounds = data.get("PC_Compounds", []) or data.get("InformationList", {}).get(
        "Information", []
    )
    if not compounds:
        raise PubChemError("No compound records in PubChem response")
    return compounds[0]


def _extract_cid(data: dict) -> int:
    """Return the CID from a raw PUG REST compound/name or fastformula response."""
    # compound/name/{name}/JSON wraps results in PC_Compounds
    pc_compounds = data.get("PC_Compounds", [])
    if pc_compounds:
        cid_obj = pc_compounds[0].get("id", {}).get("id", {})
        cid = cid_obj.get("cid")
        if cid is not None:
            return int(cid)

    # fastformula returns an IdentifierList
    id_list = data.get("IdentifierList", {}).get("CID", [])
    if id_list:
        return int(id_list[0])

    raise PubChemError("Could not extract CID from PubChem response")


def _get_properties(cid: int) -> dict[str, Any]:
    """Fetch the standard property set for a single CID."""
    prop_names = ",".join(_DESIRED_PROPERTIES)
    url = f"{_BASE_URL}/compound/cid/{cid}/property/{prop_names}/JSON"
    data = _fetch_json(url)
    rows = data.get("PropertyTable", {}).get("Properties", [])
    if not rows:
        raise PubChemError(f"No properties returned for CID {cid}")
    return rows[0]


# ------------------------------------------------------------------
# Public tool class
# ------------------------------------------------------------------


class PubChemTool(BaseTool):
    """Look up compounds on PubChem via PUG REST.

    Intended use-case: the Cloud Brain identifies a compound from NMR
    peaks and then calls this tool to retrieve its canonical metadata
    for downstream reasoning (retrosynthesis, safety lookup, etc.).

    Example::

        tool = PubChemTool()
        result = tool.lookup_by_name("aspirin")
        print(result["IUPACName"])  # "2-acetoxybenzoic acid"
    """

    # -- BaseTool interface ------------------------------------------------

    @property
    def name(self) -> str:
        return "pubchem"

    @property
    def description(self) -> str:
        return (
            "Look up compound metadata (CID, IUPAC name, molecular weight, "
            "SMILES, InChI) on NCBI PubChem."
        )

    def execute(self, **kwargs: Any) -> Any:
        """Dispatch to the appropriate lookup method.

        Accepted keyword arguments (checked in priority order):
          - cid (int)     -> get_compound_summary
          - name (str)    -> lookup_by_name
          - formula (str) -> lookup_by_formula

        Returns:
            dict or str depending on the dispatch target.

        Raises:
            ValueError: if none of the recognised keywords are provided.
        """
        if "cid" in kwargs:
            return self.get_compound_summary(int(kwargs["cid"]))
        if "name" in kwargs:
            return self.lookup_by_name(str(kwargs["name"]))
        if "formula" in kwargs:
            return self.lookup_by_formula(str(kwargs["formula"]))
        raise ValueError("PubChemTool.execute() requires one of: cid, name, formula")

    # -- Lookup methods ----------------------------------------------------

    def lookup_by_name(self, name: str) -> dict[str, Any]:
        """Search PubChem by compound name.

        Args:
            name: Common or IUPAC compound name (e.g. "aspirin", "ethanol").

        Returns:
            Dict with keys: CID, IUPACName, MolecularFormula,
            MolecularWeight, CanonicalSMILES, IsomericSMILES, InChI, InChIKey.

        Raises:
            PubChemError: if the compound is not found or the API fails.
        """
        encoded = urllib.request.quote(name, safe="")
        url = f"{_BASE_URL}/compound/name/{encoded}/JSON"
        data = _fetch_json(url)
        cid = _extract_cid(data)
        props = _get_properties(cid)
        logger.info("PubChem lookup by name %r -> CID %d", name, cid)
        return props

    def lookup_by_formula(self, formula: str) -> dict[str, Any]:
        """Search PubChem by molecular formula.

        Uses the *fastformula* endpoint which returns exact-match CIDs.

        Args:
            formula: Molecular formula string (e.g. "C9H8O4").

        Returns:
            Dict with compound properties for the first matching CID.

        Raises:
            PubChemError: if no matches are found or the API fails.
        """
        encoded = urllib.request.quote(formula, safe="")
        url = f"{_BASE_URL}/compound/fastformula/{encoded}/JSON"
        data = _fetch_json(url)
        cid = _extract_cid(data)
        props = _get_properties(cid)
        logger.info("PubChem lookup by formula %r -> CID %d", formula, cid)
        return props

    def get_compound_summary(self, cid: int) -> str:
        """Return a human-readable summary for a compound.

        Intended for inclusion in Cloud Brain prompts so the LLM has
        structured context about the identified compound.

        Args:
            cid: PubChem Compound ID.

        Returns:
            Multi-line plain-text summary string.

        Raises:
            PubChemError: if the CID is invalid or the API fails.
        """
        props = _get_properties(cid)

        iupac = props.get("IUPACName", "N/A")
        formula = props.get("MolecularFormula", "N/A")
        weight = props.get("MolecularWeight", "N/A")
        # PUG REST may return the key as "CanonicalSMILES" or "SMILES"
        smiles = props.get("CanonicalSMILES") or props.get("SMILES") or "N/A"
        inchi = props.get("InChI", "N/A")
        inchi_key = props.get("InChIKey", "N/A")

        lines = [
            f"PubChem CID: {cid}",
            f"IUPAC Name:  {iupac}",
            f"Formula:     {formula}",
            f"Weight:      {weight}",
            f"SMILES:      {smiles}",
            f"InChI:       {inchi}",
            f"InChIKey:    {inchi_key}",
        ]
        return "\n".join(lines)
