# Agilent ChemStation Result XML investigation

- Decision date: 2026-08-17
- Decision: **Experimental GO** for one exact standalone result profile
- Raw sibling requirement: none
- General ChemStation/OpenLab XML support: not claimed

## Evidence

The pinned GC2ASM test resource provides one lawful external Result XML fixture under
the repository's CeCILL-2.1 terms. Its exact size and SHA-256 are immutable controlled-
CI gates. Privacy-bearing run fields keep the native file outside Git, packages, logs,
workbooks and Actions artifacts.

The Agilent OpenLAB CDS ChemStation Edition XML Connectivity Guide establishes the XML
result/schema semantics, including the calibrated compound-name role used for
`Peak/Name`. The actual fixture independently establishes the exact C.01.10 field
shape, source labels, units, table cardinality and duplicate-row equations used by the
adapter. No third-party parser is a runtime dependency or source-code basis.

## Capability decision

GO:

- exact UTF-16LE/XML/profile detection and bounded rejection;
- standalone result conversion without a `.CH` sibling;
- source-order measured RT, area, height and integration boundaries;
- explicit min, pA\*s and pA units;
- optional calibrated compound names;
- common `Peaks`, compound `Peak_Matrix`, and conditional `Peak_Order_Matrix` output;
- batch isolation, full SHA-256 provenance and privacy-safe public identities.

Unsupported:

- other ChemStation/OpenLab revisions or XML report layouts;
- multiple signals, other detectors/channels or quantitation modes;
- raw signal extraction or pairing;
- recalculation, calibration, integration, identification, quantitation algorithms,
  write support, or umbrella Agilent compatibility.

Verified promotion requires additional independent actual result files spanning lawful
profile variations and full source-to-canonical regression. The single fixture's 36
rows are a golden check, not a fixed parser count.
