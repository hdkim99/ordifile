# Shimadzu LabSolutions-compatible `.LCD`, TTFL profile (Experimental)

## What this adapter reads

`.LCD` compound documents carry **several unrelated internal architectures**, named
after the storage the acquisition data lives in. Two are supported:

| Architecture | Storage | Shape |
| --- | --- | --- |
| **TTFL** | `TTFL Raw Data` | fixed 32-slot channel array with a per-channel chain index |
| **TLM** | `TLM Raw Data` | a single total-ion trace beside its own retention axis |

Others are refused by name with `SHIMADZU_LCD_ARCHITECTURE_UNSUPPORTED`; `QTFL
RawData`, written by QTOF instruments, is the one observed so far. A document
carrying both supported identities is refused as
`SHIMADZU_LCD_ARCHITECTURE_AMBIGUOUS`, because nothing says which storage would
hold the acquisition.

It emits one uninterpolated scientific signal per populated acquisition channel,
with retention time in minutes. It does not read peaks, does not export MS
spectra, and does not integrate anything.

## `File Property` comes in two forms

Older documents store a fixed ASCII schema token at offset 4 (`3.00` observed).
Newer ones store XML whose first `szVersion` element is an `@StoX@` prefix followed
by the version's own bytes in hexadecimal (`5.01` observed). Both are decoded; a
malformed or unreadable one fails closed.

## Channels (TTFL)

Channels occupy a **fixed 32-slot array**, `TIC Data 0` through `TIC Data 31`;
unused slots exist as zero-byte streams. Each populated slot becomes its own
channel, named after the vendor stream it came from. This follows the document's
own structure rather than inventing a channel concept.

Each channel stream is a 768-byte header, whose first field is a `u64` scan
count, followed by 16-byte records:

| Offset | Type | Field |
| --- | --- | --- |
| 0 | u64 LE | Intensity |
| 8 | u32 LE | A second intensity, never greater than the first |
| 12 | u32 LE | **Meaning not established; deliberately not read** |

Only the `u64` intensity is exported as the signal. The second intensity is
validated (`<=` the first) but not exported, because its meaning is not
established. The stored intensity has **no recorded physical unit**, so the
series carries none.

The TLM architecture has no slot array and no chain index. It stores one total-ion
trace as plain `u64` values, one per entry of its own retention axis, and the two
lengths must agree exactly or the file fails closed.

## How a TTFL channel gets its retention times

`Data Index` is an array of 16-byte records, `[u64 offset into MS Raw Data]`,
`[i32 scan index]`, `[i32 previous record in this channel's chain]`, where `-1`
marks a chain head. The records form one linked chain per channel.

A channel's stored array covers a **contiguous window of the shared retention
axis**, and that window is exactly the scan span of its chain:

    retention_index = channel_array_index + first_scan_index_of_its_chain

The adapter validates this: a channel whose declared count disagrees with its
chain's span fails closed.

## Sparse channels

A channel may acquire at only some scans inside its window. Scans it did not
acquire are stored with a zero intensity, which is **preserved as stored** and
never interpolated. Such a document raises `SHIMADZU_LCD_SPARSE_CHANNEL`.

## Retention grid

The axis is required to be strictly increasing but **not** uniform. A scan at
which a second channel also acquires costs the instrument extra time, so its step
is longer. The `retention_time_grid_uniform` metadata key reports which case a
file is, alongside the minimum and maximum observed step.

## Not claimed

Peaks, compound identities, MS spectra, quantitation, the TLM architecture, the
physical intensity unit, acquisition timestamps, and write support.
