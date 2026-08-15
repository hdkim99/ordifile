# Project landscape

- Research date: 2026-08-15
- Scope: maintained open-source chromatography and mass-spectrometry conversion
  projects, their actual support boundaries, and their repository licenses.
- Source details: exact page titles, owners, source types, dates when available, URLs,
  and access date are consolidated in [`source-register.md`](source-register.md).

## Evidence summary

| Project | Owner / source | Verified scope | License and maintenance | LabConvert decision |
|---|---|---|---|---|
| [OpenChrom](https://github.com/OpenChrom/openchrom) and [converter site](https://converter.openchrom.net/) | OpenChrom | Chromatography/MS analysis platform with format-converter plugins | Repository LICENSE is EPL-2.0; repository active in August 2026 | Do not copy code. LabConvert remains a smaller batch-to-Excel tool. |
| [chromConverter](https://github.com/ethanbass/chromConverter) | ethanbass | R conversion workflows for HPLC/GC/MS through internal and external parsers | GPL-3.0; release 0.9.0 in 2026 | Comparison reference only; no code reuse in the Apache-only core. |
| [Entab](https://github.com/bovee/entab) and [PyPI](https://pypi.org/project/entab/) | bovee | Record parser for several instrument formats, including ChemStation CH/FID | MIT; active source, but PyPI 0.3.3 wheel/platform coverage is limited | Do not make it a v0.1 dependency. Re-evaluate with lawful fixtures. |
| [rainbow](https://github.com/evanyeyeye/rainbow) and [format list](https://rainbow-api.readthedocs.io/en/latest/formats.html) | evanyeyeye | Signal/spectrum arrays for listed chromatography formats | LGPL-3.0; active | The broad format list does not imply peak-table or complete metadata support. |
| [ThermoRawFileParser](https://github.com/CompOmics/ThermoRawFileParser) | CompOmics | Thermo MS RAW conversion to open MS formats | Apache-2.0, but uses a separately licensed vendor reader | Not evidence for general GC-FID support; never bundle vendor binaries. |
| [ProteoWizard](https://github.com/ProteoWizard/pwiz) | ProteoWizard | Mass-spectrometry conversion, including vendor readers | Apache-2.0 core; vendor components have separate conditions | Future GC-MS context only. |
| [HUPO-PSI mzML](https://github.com/HUPO-PSI/mzML) | HUPO-PSI | Open mass-spectrometry spectrum and metadata standard | Open maintained specification | Future GC-MS adapter candidate, not generic GC support. |

## Verified facts, inference, and uncertainty

- Verified: projects that name a vendor often expose only signals, spectra, or MS
  conversion—not metadata, integrated peaks, and write support together.
- Inference: LabConvert can differentiate through a narrow deterministic workflow,
  transparent partial failures, and a simple adapter API rather than format count.
- Unresolved: no competitor fixture was shown to have clear redistribution provenance
  sufficient for reuse here.
- Risk: GPL, LGPL, EPL, and vendor-library obligations differ. No external source code
  or vendor runtime is copied or bundled.
