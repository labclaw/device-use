"""Cloud Brain for NMR — uses Claude to interpret spectra and suggest experiments."""

import sys
from collections.abc import Generator

from anthropic import Anthropic

from device_use.instruments.nmr.processor import NMRProcessor, NMRSpectrum


NMR_SYSTEM_PROMPT = """You are an expert NMR spectroscopist and analytical chemist working as part of an AI scientist system called Device-Use.

You receive processed NMR data (peak lists with chemical shifts and relative intensities) and must:
1. Analyze the peak pattern (chemical shifts, relative intensities, splitting patterns if available)
2. Identify functional groups present
3. Propose candidate structures (provide IUPAC name and common name)
4. Assess confidence in your identification
5. Suggest next experiments to confirm the structure

Important guidelines:
- Be specific about chemical shift assignments (e.g., "δ 7.2-7.4 indicates aromatic protons")
- Use standard NMR terminology
- When uncertain, clearly state your confidence level
- Always suggest at least one follow-up experiment (13C, COSY, HSQC, HMBC, etc.)
- If a molecular formula is provided, use it to constrain your analysis
- Consider the solvent when interpreting chemical shifts

Format your response as:
## Peak Analysis
[Detailed peak-by-peak analysis]

## Proposed Structure
[Most likely structure with reasoning]

## Confidence
[High/Medium/Low with explanation]

## Recommended Next Steps
[Specific experiments to run next and why]
"""


class NMRBrain:
    """Cloud Brain for NMR interpretation — wraps Claude API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = Anthropic()
        self.model = model
        self._processor = NMRProcessor()

    def _build_summary(self, spectrum: NMRSpectrum) -> str:
        return self._processor.get_spectrum_summary(spectrum)

    def _call(self, system: str, user_message: str, max_tokens: int = 2000) -> str:
        """Non-streaming API call."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def _stream(self, system: str, user_message: str, max_tokens: int = 2000) -> Generator[str]:
        """Streaming API call — yields text chunks."""
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    def interpret_spectrum(
        self,
        spectrum: NMRSpectrum,
        molecular_formula: str | None = None,
        context: str = "",
        stream: bool = False,
    ) -> str | Generator[str]:
        """Send spectrum data to Claude for interpretation."""
        summary = self._build_summary(spectrum)

        user_message = f"Please analyze this NMR spectrum:\n\n{summary}"
        if molecular_formula:
            user_message += f"\n\nMolecular formula: {molecular_formula}"
        if context:
            user_message += f"\n\nAdditional context: {context}"

        if stream:
            return self._stream(NMR_SYSTEM_PROMPT, user_message)
        return self._call(NMR_SYSTEM_PROMPT, user_message)

    def suggest_next_experiment(
        self,
        spectrum: NMRSpectrum,
        hypothesis: str = "",
        stream: bool = False,
    ) -> str | Generator[str]:
        """Given current data, suggest the most informative next experiment."""
        summary = self._build_summary(spectrum)

        user_message = (
            f"Based on this NMR data, what experiment should I run next?\n\n"
            f"{summary}"
        )
        if hypothesis:
            user_message += f"\n\nCurrent hypothesis: {hypothesis}"
        user_message += (
            "\n\nProvide a specific recommendation with:\n"
            "1. Which experiment (COSY, HSQC, HMBC, 13C, DEPT, NOESY, etc.)\n"
            "2. Why this experiment is most informative right now\n"
            "3. What specific question it will answer\n"
            "4. Expected key correlations to look for"
        )

        if stream:
            return self._stream(NMR_SYSTEM_PROMPT, user_message, max_tokens=1500)
        return self._call(NMR_SYSTEM_PROMPT, user_message, max_tokens=1500)

    def compare_spectra(
        self, spectrum1: NMRSpectrum, spectrum2: NMRSpectrum, context: str = ""
    ) -> str:
        """Compare two NMR spectra — for purity/batch comparison."""
        summary1 = self._build_summary(spectrum1)
        summary2 = self._build_summary(spectrum2)

        user_message = (
            f"Compare these two NMR spectra and identify any differences:\n\n"
            f"--- Spectrum 1 ---\n{summary1}\n\n"
            f"--- Spectrum 2 ---\n{summary2}"
        )
        if context:
            user_message += f"\n\nContext: {context}"

        return self._call(NMR_SYSTEM_PROMPT, user_message)
