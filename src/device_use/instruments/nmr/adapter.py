"""TopSpin NMR adapter — three control modes for the same instrument.

Control Modes:
  API:     gRPC to running TopSpin (port 3081) — fast, programmatic
  GUI:     Computer Use visual automation of TopSpin GUI — wow factor
  Offline: nmrglue processing, no TopSpin needed — works anywhere

All three modes produce the same NMRSpectrum output.
"""

from pathlib import Path
from typing import Any

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo
from device_use.instruments.nmr.processor import NMRProcessor, NMRSpectrum


class TopSpinAdapter(BaseInstrument):
    """Interface to TopSpin NMR software.

    Supports three control modes:
      - API: gRPC to running TopSpin (requires TopSpin GUI running)
      - GUI: Computer Use visual automation (requires TopSpin GUI visible)
      - Offline: nmrglue processing (no TopSpin needed at all)
    """

    def __init__(
        self,
        topspin_dir: str = "/opt/topspin5.0.0",
        mode: ControlMode | str = ControlMode.OFFLINE,
    ):
        self.topspin_dir = Path(topspin_dir)
        self.examdata_dir = self.topspin_dir / "examdata"
        self.processor = NMRProcessor()
        self._topspin = None
        self._dp = None
        self._gui = None
        self._connected = False
        self._mode = ControlMode(mode) if isinstance(mode, str) else mode

    def info(self) -> InstrumentInfo:
        return InstrumentInfo(
            name="TopSpin",
            vendor="Bruker",
            instrument_type="nmr",
            supported_modes=[ControlMode.API, ControlMode.GUI, ControlMode.OFFLINE],
            version="5.0.0",
            description="Bruker TopSpin NMR acquisition and processing software",
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> ControlMode:
        return self._mode

    def connect(self) -> bool:
        """Try to connect based on current mode.

        For OFFLINE mode, always succeeds if examdata dir exists.
        For API mode, tries gRPC connection to TopSpin.
        For GUI mode, checks if TopSpin window is visible.
        """
        if self._mode == ControlMode.OFFLINE:
            self._connected = self.examdata_dir.exists()
            return self._connected

        if self._mode == ControlMode.API:
            return self._connect_api()

        if self._mode == ControlMode.GUI:
            return self._connect_gui()

        return False

    def _connect_api(self) -> bool:
        """Connect via gRPC to running TopSpin."""
        try:
            from bruker.api.topspin import Topspin

            self._topspin = Topspin()
            self._dp = self._topspin.getDataProvider()
            _ = self._topspin.getVersion()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    def _connect_gui(self) -> bool:
        """Check if TopSpin GUI is visible for Computer Use."""
        try:
            from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation

            self._gui = TopSpinGUIAutomation()
            if not self._gui.available:
                return False
            found = self._gui.detect_topspin_window()
            self._connected = found
            return found
        except Exception:
            self._connected = False
            return False

    def list_datasets(self) -> list[dict[str, Any]]:
        """List available example datasets."""
        return self.list_examdata()

    def list_examdata(self) -> list[dict]:
        """List available example datasets from TopSpin examdata."""
        datasets = []
        if not self.examdata_dir.exists():
            return datasets
        for sample_dir in sorted(self.examdata_dir.iterdir()):
            if not sample_dir.is_dir():
                continue
            for expno_dir in sorted(sample_dir.iterdir()):
                if not expno_dir.is_dir() or not expno_dir.name.isdigit():
                    continue
                fid_path = expno_dir / "fid"
                if not fid_path.exists():
                    continue
                title = ""
                title_path = expno_dir / "pdata" / "1" / "title"
                if title_path.exists():
                    title = title_path.read_text().strip().split("\n")[0]
                datasets.append(
                    {
                        "path": str(expno_dir),
                        "sample": sample_dir.name,
                        "expno": int(expno_dir.name),
                        "title": title,
                    }
                )
        return datasets

    def acquire(self, **kwargs) -> Any:
        """Acquire NMR data (start experiment).

        Only available in API and GUI modes — offline mode works
        with existing data only.
        """
        if self._mode == ControlMode.OFFLINE:
            raise RuntimeError("Cannot acquire data in offline mode")
        if self._mode == ControlMode.API:
            return self._acquire_api(**kwargs)
        if self._mode == ControlMode.GUI:
            return self._acquire_gui(**kwargs)

    def _acquire_api(self, **kwargs) -> Any:
        """Start acquisition via gRPC API."""
        # TODO: Implement zg (acquire) via TopSpin API
        raise NotImplementedError("API acquisition not yet implemented")

    def _acquire_gui(self, **kwargs) -> Any:
        """Start acquisition via Computer Use GUI automation."""
        # TODO: Click buttons in TopSpin GUI to start acquisition
        raise NotImplementedError("GUI acquisition not yet implemented")

    def process(self, data_path: str, **kwargs) -> NMRSpectrum:
        """Process a dataset using the current control mode."""
        return self.process_dataset(data_path)

    def process_dataset(self, dataset_path: str) -> NMRSpectrum:
        """Process a dataset — routes to the appropriate backend."""
        if self._mode == ControlMode.API and self._connected:
            return self._process_via_api(dataset_path)
        if self._mode == ControlMode.GUI and self._connected:
            return self._process_via_gui(dataset_path)
        # Offline mode (or fallback)
        return self._process_via_nmrglue(dataset_path)

    def _process_via_nmrglue(self, dataset_path: str) -> NMRSpectrum:
        """Process using nmrglue (offline, no TopSpin needed)."""
        dic, fid = self.processor.read_bruker(dataset_path)
        return self.processor.process_1d(dic, fid, dataset_path=dataset_path)

    def _process_via_api(self, dataset_path: str) -> NMRSpectrum:
        """Process using TopSpin gRPC API (live, requires running TopSpin)."""
        nmrdata = self._dp.getNMRData(dataset_path)
        nmrdata.launch("efp")      # exponential multiply + FFT + phase
        nmrdata.launch("apbk -n")  # neural-net auto phase + baseline
        nmrdata.launch("ppf")      # peak picking
        # Read back processed data via nmrglue for consistent output format
        return self._process_via_nmrglue(dataset_path)

    def _process_via_gui(self, dataset_path: str) -> NMRSpectrum:
        """Process using Computer Use GUI automation.

        Visually operates the TopSpin GUI:
        1. Open the dataset via command line
        2. Run efp (FT + phase)
        3. Run apbk (auto phase + baseline)
        4. Run ppf (peak picking)
        5. Read back result via nmrglue
        """
        self._gui.open_dataset(dataset_path)
        self._gui.process_spectrum()
        # Read back the processed data using nmrglue
        return self._process_via_nmrglue(dataset_path)
