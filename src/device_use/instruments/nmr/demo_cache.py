"""Pre-cached Claude responses for NMR demo compounds.

These responses allow the demo to run fully end-to-end without an
ANTHROPIC_API_KEY.  Each entry contains an ``interpret`` response and a
``suggest_next_experiment`` response, keyed by lowercase compound name.

Matching logic in NMRBrain tries (in order):
  1. Exact match on spectrum.title (lowercased)
  2. Exact match on spectrum.sample_name (lowercased)
  3. Substring match against both fields

This means TopSpin datasets whose title or sample_name contains
"alpha ionone" or "strychnine" will hit the cache automatically.
"""

DEMO_RESPONSES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------
    # Alpha Ionone  (C13H20O)  --  CDCl3, 400 MHz
    # ------------------------------------------------------------------
    "alpha ionone": {
        "interpret": """\
## Peak Analysis

| Chemical Shift (ppm) | Assignment | Reasoning |
|---|---|---|
| 7.29 | Residual CHCl3 (solvent) | Characteristic CDCl3 residual solvent peak at exactly 7.26\u20137.29 ppm; no aromatic protons expected for alpha-ionone. |
| 6.62 | H-4 (=CH\u2013C=O) | Downfield vinyl proton conjugated with the carbonyl. In alpha-ionone the C3=C4 double bond is conjugated with the C5=O, placing this proton at 6.5\u20136.7 ppm. Doublet expected (J ~ 16 Hz, trans). |
| 6.05 | H-3 (=CH\u2013) | Second vinyl proton of the conjugated diene system. The 0.57 ppm downfield shift from an isolated vinyl proton reflects partial conjugation with the ring double bond. Doublet of doublets expected. |
| 5.49 | H-2 (ring =CH\u2013) | Trisubstituted olefinic proton on the cyclohexene ring (C1=C2). Appears as a broad singlet or multiplet. Consistent with delta 5.4\u20135.6 for trisubstituted alkenes. |
| 2.23 | H-6ax/H-6eq (ring CH2 adjacent to C=O) | Alpha to carbonyl (C5=O). The electron-withdrawing effect of the ketone shifts these methylene protons to ~2.2 ppm. |
| 2.02 | H-7 (=C\u2013CH3 or ring CH2) | Allylic methylene protons on the ring, adjacent to the C1=C2 double bond. Moderate deshielding from allylic position. |
| 1.54 | Ring CH2 protons (H-8/H-9) | Methylene protons in the saturated portion of the cyclohexene ring. Standard aliphatic shift. |
| 0.83 | Gem-dimethyl (C10, C11) or C-12 methyl | High-field singlet (6H) from the two equivalent methyl groups on the quaternary carbon of the ring. The slight upfield shift from ~0.9 is consistent with a shielded gem-dimethyl environment. |

**Integration pattern**: The peak intensity ratios are consistent with C13H20O (degree of unsaturation = 4: one ring + three double bonds/carbonyl equivalent, matching one C=O + two C=C).

## Proposed Structure

**Alpha-Ionone** (trans-alpha-Ionone)
- IUPAC: (E)-4-(2,6,6-trimethylcyclohex-2-en-1-yl)but-3-en-2-one
- CAS: 127-41-3
- Molecular formula: C13H20O (MW 192.30)

The compound is a monocyclic terpenoid ketone found in violet and iris essential oils. The spectrum matches all key features:
- Conjugated enone system (H-4 at 6.62, H-3 at 6.05)
- Trisubstituted ring olefin (H-2 at 5.49)
- Gem-dimethyl group (0.83 ppm, high intensity)
- No aromatic protons (7.29 is solvent)

## Confidence

**High** \u2014 The chemical shift pattern, particularly the conjugated enone vinyl protons at 6.62/6.05 ppm paired with the trisubstituted ring alkene at 5.49 ppm and the signature gem-dimethyl singlet near 0.83 ppm, is highly diagnostic for alpha-ionone. The molecular formula C13H20O is fully consistent.

## Recommended Next Steps

1. **13C{1H} NMR (CDCl3, 100 MHz)**: Confirm the carbonyl carbon (~198 ppm), four olefinic carbons (120\u2013160 ppm), and the quaternary gem-dimethyl carbon (~34 ppm). This will definitively distinguish alpha-ionone from beta-ionone, which has a different carbonyl chemical shift.

2. **COSY (1H\u20131H correlation)**: Confirm the H3\u2013H4 coupling across the enone and the connectivity of ring protons. Key correlation: H-4 (6.62) \u2194 H-3 (6.05).

3. **GC-MS**: Confirm molecular ion at m/z 192 and compare fragmentation pattern to the NIST library entry for alpha-ionone (base peak at m/z 121 from retro-Diels\u2013Alder).\
""",
        "suggest_next_experiment": """\
## Recommended Next Experiment: 13C{1H} NMR

### Why This Experiment

The 1H spectrum provides strong evidence for alpha-ionone, but a 13C spectrum will provide definitive structural confirmation. Alpha-ionone and beta-ionone have very similar 1H spectra (both show conjugated vinyl protons and gem-dimethyl groups), but their 13C spectra are clearly distinguishable, particularly at the carbonyl and olefinic carbons.

### What It Will Answer

1. **Carbonyl confirmation**: Alpha-ionone shows C=O at ~198 ppm; beta-ionone at ~197 ppm with different olefinic carbon patterns.
2. **Number of unique carbons**: Should observe exactly 13 unique carbon resonances for alpha-ionone (no molecular symmetry).
3. **Quaternary carbon identification**: The gem-dimethyl quaternary carbon at ~34 ppm is diagnostic.

### Expected Key Signals

| Carbon | Expected Shift (ppm) | Type |
|---|---|---|
| C=O (C-5) | ~198 | Quaternary |
| C-4 (=CH) | ~154 | CH |
| C-1 (=C<) | ~137 | Quaternary |
| C-2 (=CH) | ~126 | CH |
| C-3 (=CH) | ~131 | CH |
| C-gem (C-9) | ~34 | Quaternary |
| Gem-dimethyl | ~28 | CH3 x2 |
| COCH3 | ~27 | CH3 |

### Experimental Parameters

- **Nucleus**: 13C (100.6 MHz at 9.4 T / 400 MHz 1H)
- **Solvent**: CDCl3 (reference: 77.0 ppm)
- **Scans**: 1024\u20132048 (for adequate S/N on quaternary carbons)
- **Relaxation delay**: 2 s
- **Acquisition time**: ~1.5 hours

If 13C confirms the structure, follow up with **DEPT-135** to classify CH3/CH2/CH/C multiplicities without needing additional sample.\
""",
    },
    # ------------------------------------------------------------------
    # Strychnine  (C21H22N2O2)  --  CDCl3, 400 MHz
    # ------------------------------------------------------------------
    "strychnine": {
        "interpret": """\
## Peak Analysis

| Chemical Shift (ppm) | Assignment | Reasoning |
|---|---|---|
| 8.10 | H-12 (aromatic, peri to N) | Most downfield aromatic proton. In strychnine, H-12 is deshielded by the peri relationship to the N-oxide-like nitrogen lone pair and by the anisotropic effect of the adjacent carbonyl. Appears as a doublet (J ~ 7.5 Hz). |
| 7.24 | H-15 or H-14 (aromatic) | Mid-range aromatic proton in the indole-derived ring system. Overlaps with CDCl3 residual signal. Triplet or doublet of doublets expected. |
| 7.15 | H-13 or H-14 (aromatic) | Second mid-range aromatic proton. Part of the ABCD spin system of the benzene ring. |
| 5.88 | H-22 (olefinic =CH) | Vinyl proton of the isolated C=C double bond (C22=C23) in the Strychnos skeleton. Appears as a broad singlet or narrow multiplet, characteristic of a strained bridgehead olefin. |
| 4.27 | H-23a (=C\u2013CH2\u2013O) | One of the diastereotopic protons of the allylic oxymethylene group. Downfield due to both the oxygen and the adjacent double bond. |
| 4.07 | H-23b (=C\u2013CH2\u2013O) | Geminal partner of H-23a. The ~0.2 ppm separation between 4.27 and 4.07 reflects the diastereotopic environment in the rigid bicyclic framework. |
| 3.92 | H-8 (N\u2013CH\u2013C=O) | Proton alpha to both nitrogen and the amide carbonyl. The combined deshielding from N and C=O places this proton at ~3.9 ppm. |
| 3.85 | H-16a (N\u2013CH2) | One proton of the N-methylene adjacent to the tertiary amine nitrogen. |
| 3.68 | H-11a (ArCH) | Benzylic proton at the junction of the aromatic ring and the aliphatic framework. |
| 3.12 | H-16b (N\u2013CH2) | Geminal partner of H-16a, shifted upfield due to different orientation relative to nitrogen lone pair. |
| 2.84 | H-11b or H-17a | Aliphatic CH in the cage structure, moderately deshielded by proximity to nitrogen. |
| 2.68 | H-17b or H-18a | Cage methylene proton. Moderate deshielding from strain effects. |
| 2.32 | H-18b or H-20a | Methylene proton in the cyclohexane portion of the cage. |
| 1.86 | H-20b | Aliphatic cage proton, relatively shielded. |
| 1.41 | H-15a/H-14a (cage CH2) | Upfield methylene protons in the most shielded part of the cage structure. |
| 1.24 | H-15b/H-14b (cage CH2) | Most shielded cage protons, furthest from electronegative atoms. |

**Key observations**: 16 resolved peaks for C21H22N2O2 (degree of unsaturation = 12: consistent with the heptacyclic strychnine skeleton). The 1H spectrum of strychnine is a classic benchmark\u2014every proton is in a unique chemical environment due to the rigid cage.

## Proposed Structure

**Strychnine**
- IUPAC: (4aR,5aS,8aR,13aS,15aS,15bR)-4a,5,5a,7,8,13a,15,15a,15b,16-decahydro-2H-4,6-methanoindolo[3,2,1-ij]oxepino[2,3,4-de]pyrrolo[2,3-h]quinoline-14-one
- CAS: 57-24-9
- Molecular formula: C21H22N2O2 (MW 334.42)

Strychnine is a highly toxic indole alkaloid from *Strychnos nux-vomica*. Its heptacyclic structure creates an extremely rigid molecular framework where all 22 protons are chemically inequivalent. The spectrum is a textbook example used worldwide for NMR benchmarking.

Key structural confirmations:
- Aromatic protons (8.10, 7.24, 7.15) consistent with 1,2-disubstituted benzene
- Olefinic proton (5.88) from the strained alkene
- Diastereotopic oxymethylene (4.27/4.07) flanking the lactam oxygen
- Spread of aliphatic signals (1.2\u20133.9 ppm) reflecting the cage topology

## Confidence

**High** \u2014 Strychnine's 1H NMR spectrum is one of the most well-characterized in the literature. The pattern of 16 resolved resonances spanning 1.2\u20138.1 ppm, with the distinctive downfield aromatic doublet at 8.10, the isolated vinyl singlet at 5.88, and the characteristic diastereotopic pair at 4.27/4.07, is essentially unique to this compound. The molecular formula C21H22N2O2 with 12 degrees of unsaturation confirms the heptacyclic skeleton.

## Recommended Next Steps

1. **13C{1H} NMR (CDCl3, 100 MHz)**: Should show exactly 21 distinct carbon resonances. The amide carbonyl at ~170 ppm and the olefinic carbons at ~127/140 ppm are diagnostic. This spectrum has been assigned exhaustively in the literature for comparison.

2. **1H\u201313C HSQC**: Map each proton to its directly bonded carbon. This is the standard "total assignment" experiment for strychnine, and published data is available for verification.

3. **1H\u201313C HMBC**: Confirm long-range C\u2013H correlations across the cage. Key correlation: H-12 (8.10 ppm) should show 3-bond correlation to the carbonyl carbon (~170 ppm).

4. **Optical rotation [\u03b1]D**: Confirm absolute configuration. Natural strychnine is (\u2212)-strychnine; [\u03b1]D20 = \u2212139\u00b0 (c 1, CHCl3).\
""",
        "suggest_next_experiment": """\
## Recommended Next Experiment: 1H\u201313C HSQC

### Why This Experiment

Strychnine is a heptacyclic alkaloid where all 22 protons resonate in unique chemical environments. While the 1H spectrum is highly characteristic, a 2D HSQC experiment provides the definitive one-bond C\u2013H correlation map needed for complete structural verification. This is the gold standard experiment for strychnine assignment and has extensive literature data for comparison.

### What It Will Answer

1. **Unambiguous CH assignment**: Each of the 16 resolved 1H peaks will correlate to its directly attached 13C, resolving any ambiguity in the 1D assignments.
2. **Multiplicity editing**: HSQC with multiplicity editing (DEPT-edited HSQC) distinguishes CH/CH3 (positive phase) from CH2 (negative phase), immediately classifying each carbon type.
3. **Benchmark validation**: The complete HSQC of strychnine has been published extensively; comparison confirms identity with absolute certainty.

### Expected Key Correlations

| 1H Shift (ppm) | Expected 13C Shift (ppm) | Assignment |
|---|---|---|
| 8.10 | ~122 | C-12 (ArCH) |
| 7.24 | ~128 | C-14 (ArCH) |
| 7.15 | ~124 | C-13 (ArCH) |
| 5.88 | ~127 | C-22 (=CH) |
| 4.27 / 4.07 | ~50 | C-23 (CH2, negative in DEPT-HSQC) |
| 3.92 | ~60 | C-8 (CH) |
| 3.12 / 3.85 | ~42 | C-16 (CH2) |

### Experimental Parameters

- **Experiment**: HSQC with multiplicity editing (Bruker pulse program: hsqcedetgpsisp2.3)
- **Nucleus**: 1H\u201313C
- **Solvent**: CDCl3
- **F2 (1H) sweep width**: 0\u201310 ppm (4006 Hz at 400 MHz)
- **F1 (13C) sweep width**: 0\u2013180 ppm (18054 Hz at 100 MHz)
- **Data points**: 2048 (F2) x 256 (F1)
- **Scans per increment**: 4\u20138
- **Acquisition time**: ~45 minutes

After HSQC, proceed to **HMBC** for long-range correlations to confirm connectivity across the cage bonds and assign quaternary carbons.\
""",
    },
}


_DNMR_ANALYSIS = """\
## Dynamic NMR Analysis: N,N-Dimethylacetamide (DMA)

### Temperature-Dependent Behavior

The variable-temperature 1H NMR spectra of N,N-dimethylacetamide reveal the classic \
signature of restricted rotation about the amide C–N bond:

| Temperature | N-Methyl Region | Interpretation |
|---|---|---|
| 283 K (T=10) | Two distinct singlets (~2.9, ~3.0 ppm) | **Slow exchange** — rotation frozen on NMR timescale |
| 320 K | Two peaks, slightly broadened | Approaching coalescence |
| 350 K | Broad, coalescing peaks | **Near coalescence temperature (Tc)** |
| 370 K | Single broad peak | Just past coalescence |
| 420 K | Sharp singlet | **Fast exchange** — free rotation |

### Physical Chemistry

The amide bond in DMA has partial double-bond character (~40% C=N) due to \
nitrogen lone pair delocalization into the carbonyl π* orbital. This creates \
a rotational barrier (ΔG‡ ≈ 70–75 kJ/mol) that:

1. At **low temperature**: Freezes the two N-methyl groups in distinct \
environments (cis vs trans to C=O), giving two NMR peaks
2. At **coalescence**: Exchange rate matches the frequency difference between peaks
3. At **high temperature**: Rapid rotation averages the two environments

### Barrier Calculation

From the coalescence temperature (Tc ≈ 350 K) and the chemical shift \
difference (Δν ≈ 40 Hz at 400 MHz):

- **k(Tc) = π × Δν / √2 ≈ 89 s⁻¹**
- **ΔG‡ = R × Tc × [22.96 + ln(Tc/Δν)] ≈ 73 kJ/mol**

This is consistent with the literature value of 71–75 kJ/mol for DMA.

### Significance

This DNMR experiment is a cornerstone of physical organic chemistry education, \
demonstrating that NMR can measure reaction rates and activation energies for \
processes occurring on the millisecond timescale. The device-use middleware \
makes this experiment fully automatable — from temperature control to data \
acquisition to barrier calculation.\
"""


def get_dnmr_analysis() -> str:
    """Return cached DNMR temperature series analysis."""
    return _DNMR_ANALYSIS


def find_cached_response(
    compound_name: str,
    response_type: str = "interpret",
) -> str | None:
    """Look up a cached response by compound name.

    Args:
        compound_name: Name to match (case-insensitive). Checked as
            exact key first, then as substring in cache keys.
        response_type: ``"interpret"`` or ``"suggest_next_experiment"``.

    Returns:
        The cached response text, or ``None`` if no match found.
    """
    key = compound_name.strip().lower()

    # 1. Exact match
    if key in DEMO_RESPONSES:
        return DEMO_RESPONSES[key].get(response_type)

    # 2. Substring match (either direction)
    for cache_key, responses in DEMO_RESPONSES.items():
        if cache_key in key or key in cache_key:
            return responses.get(response_type)

    return None
