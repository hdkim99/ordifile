# Agilent ChemStation `.CH` v181 independent implementation notes

- Date: 2026-08-16
- Implementation boundary: Experimental structural decoded records
- Exact fixture: `298146` bytes, SHA-256
  `9abeb86b09d54c10e81f46648804acc0319b6e1d014cee54034eae91331f97ef`
- Normalized oracle summary:
  [`reference_results/agilent-ch-v181.json`](reference_results/agilent-ch-v181.json)

These notes specify an independently written implementation. Public readers were used
as output oracles; their source code was not copied, translated, vendored, imported,
or executed by Ordifile at runtime. This is an engineering provenance boundary, not a
claim of a formally certified legal clean-room process.

## Bounded structural fields

| Byte range or offset | Observed value | Interpretation | Confidence | Reference agreement | Test |
|---|---|---|---|---|---|
| `0..3` | Pascal ASCII `181` | internal version text | High | reader consensus | positive, conflict, unsupported |
| `248..251` | BE `u32` 181 | second version field | High for this profile | exact fixture observation; reader interpretations differ | positive, conflict |
| `264..267` | BE `u32` 13 | data page; `(13-1)*512=6144` | High for this profile | reader consensus | invalid page, missing payload |
| `347...` | Pascal UTF-16LE `GC DATA FILE` | required family marker | High for this profile | exact fixture observation and chemplexity field map | absent marker, malformed text |
| `3089...` | Pascal UTF-16LE `Asterix ChemStation` | required producer-profile marker | High for this profile | exact fixture observation | exact-match and rejection tests |
| `6144..EOF` | mixed BE records | structural record payload | High | two readers plus independent decoder | truncation, odd EOF, limits |
| `282`, `286` | BE `f32` values | candidate axis endpoints only | Low semantic confidence | reader disagreement in output length | exact `float.hex()` text; never applied |
| `4724`, `4732` | BE `f64` values | candidate intercept/slope only | Low physical confidence | numeric transform agreement | exact `float.hex()` text; never applied |
| `4172...` | Pascal UTF-16LE `cou` | untrusted raw unit lexeme | Low | official defect warns units may be wrong | preserved; unit remains unknown |

The implemented payload grammar is:

1. read one big-endian signed 16-bit word;
2. `0x7FFF` begins an absolute record followed by signed high 16 bits and unsigned
   low 32 bits; the candidate integer is `high * 2^32 + low` and delta resets;
3. any other word updates the candidate second delta and then the candidate integer;
4. require every marker payload and exact EOF consumption;
5. retain every decoded record and reject overflow or the two-million-record cap.

The exact external fixture contains 36,500 absolute records followed by one ordinary
zero record. The last value repeats the previous value. It may be a sample or a
terminal/padding record. Ordifile retains it, marks the scientific point count
unresolved, and does not silently choose 36,500 or 36,501 scientific points.

## Reference comparison

| Implementation | Fixture execution | Records/signals | Time labels | Decision |
|---|---|---:|---:|---|
| ChromStream 0.2.0 | accepted | 36,501 | 36,501 | signal oracle; time lineage-only |
| rainbow 1.4.0 | accepted | 36,501 | 36,500 | signal oracle; time rejected as misaligned |
| Entab 0.3.3/current | rejected v181 | unavailable | unavailable | negative compatibility oracle |
| Ordifile independent decoder | accepted | 36,501 | not generated | exact structural output |

ChromStream and rainbow produce identical full decoded integer sequences. Packed as one
big-endian signed 64-bit integer (`>q`) per value, the 36,501-value sequence has SHA-256
`9d0adc5724779c8c3061da6e9523952401953d859922c4079b023072c6161667`.

ChromStream states that it adapts the chemplexity lineage; chromConverter also derives
from that lineage. Agreement within that family is not counted as independent
scientific validation. Rainbow agrees on the signal sequence but exposes a one-value
time mismatch. Consequently, no retention-time vector is exported.

## Canonical mapping

- `series_kind = decoded_records`
- x: integer ordinal `0..N-1`
- x label: `decoded_record_index`; unit `None`
- y: decoded integer before candidate slope/intercept
- y label: `decoded_raw_integer`; unit `None`
- final ambiguous record: included
- peaks: none; Ordifile performs no peak detection
- acquisition timestamp: raw local text only; century and timezone are unresolved, so no
  canonical `acquired_at` value is emitted
- FID/channel identity: only when the complete basename exactly matches the documented
  `FID<module><channel>` convention; renamed or partial names are unsupported and rejected

The workbook sheet is `Signals_Records_<detector-or-channel>`, not an ordinary
scientific `Signals_<channel>` sheet.

## Unsupported semantics and variants

- retention time, sampling interval, and run duration;
- physical/display scaling and signal unit;
- scientific point count and final-record role;
- nonzero chained relative records on a real fixture;
- detector meanings inferred from header codes;
- peak tables, `.D` directory grouping, sibling files, multiple channels;
- TCD, MS, DAD, other `.CH` versions, OpenLab as a whole, and write support.

## License boundary

ChromStream/chemplexity (MIT) and Entab (MIT) were research references.
chromConverter (GPL >= 3) and rainbow (LGPL-3.0) were comparison-only. No code from
any reference implementation is included, and no new dependency is added. Exact
pinned sources and licenses are recorded in the main investigation document.
