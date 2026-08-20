# Result fixture intake

This guide describes the privacy-first path for contributing an actual chromatography
Result/Peak Table export toward a new exact-profile adapter. Do not attach the original
scientific file, screenshot, mapping/profile/Mapping Set JSON, or generated workbook to a
public issue.
Do not attach local schema-drift screens or reports containing raw header, worksheet, profile
label, or repaired-mapping details. A fixed diagnostic category/count summary may be shared
only after the same privacy review.

## Preferred source

Use an untouched original export from one standard, calibration, or model sample when
possible. One run or injection is preferred. The table must contain explicit retention time
and area columns; height, compound, detector, and channel columns are useful but optional.
Do not edit headers, values, delimiters, encoding, or workbook structure for Ordifile.

Before parsing work begins, maintainers classify:

- software and exact version/profile;
- export menu/action and container;
- SHA-256, byte size, encoding/delimiter, header set, and row count;
- explicit RT/area fields and unit evidence;
- ownership, license, permission, and redistribution class;
- operator/analyst names, email/phone, personal sample identifiers, institution names,
  usernames, hostnames, IP/MAC addresses, local/network paths, instrument or autosampler
  serials, license/dongle IDs, and project/method paths.

User-provided fixtures remain local-only and gitignored. They are not uploaded to Actions,
package artifacts, public workbooks, or public logs. When an audit identity is needed, use
`source-<full SHA-256>` rather than the real filename. Public tests use independently invented
synthetic tables.

## Currently requested exact exports

| Target issue | Required original export |
|---|---|
| Thermo Fisher, #45 | Chromeleon 7.3.x fixed-template, one-injection Result Text containing RT and Area |
| PerkinElmer, #48 | SimplicityChrom 3.1 one-injection Result Set Review CSV or XLSX |
| PerkinElmer, #43 | TotalChrom 6.3.x one-run TX0 or ASCII-delimited Result |
| SCION, #44 | CompassCDS one-run Print Manager ASCII or Excel Result |
| LECO 1D, #47 | ChromaTOF one-run 1D Result CSV plus a lawful controlled-use basis |
| Bruker, #46 | Current EVOQ GC-TQ/TASQ one-analysis original LIMS Result container |

Only a sanitized issue summary should be public: vendor/software/version, the exact export
action, container type, result row count, whether RT/Area/units exist, permission class, and
privacy status. Maintainers will arrange a private/local inspection path if the lead is useful.
An Ordifile-generated structural fingerprint, schema versions, container, column count,
canonical role sequence, unit-presence states, and a fixed error code may be shared after
privacy review. The fingerprint contains no mapping selectors and cannot verify a vendor.

## Promotion gate

An exact-profile adapter requires lawful access to actual bytes, deterministic sample/run and
row boundaries, explicit finite RT and Area, unit evidence or an explicit unresolved state,
bounded format detection, full-row comparison, result-only workbook conversion and reopen,
generic collision protection, privacy PASS, license PASS, and independent verification. A
generic user mapping alone never satisfies this gate and never creates a vendor support claim.
