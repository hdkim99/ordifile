# ANDI/AIA chromatography `.CDF` (Experimental)

## Why this format matters

This is the first **open standard** Ordifile reads rather than a reverse-engineered
vendor container. `.CDF` is netCDF-3 (a public Unidata format) carrying the ASTM
E1947 chromatography data elements, and every major vendor exports it. One adapter
therefore covers many instruments at once.

Two consequences follow, and both are unusual for this project:

- **Units come from the file.** `detector_unit` and `retention_unit` are stored
  attributes, so the response unit is not "unknown" the way it is in the vendor
  binaries.
- **The peak table is standard-defined.** `peak_retention_time`, `peak_area`,
  `peak_height`, `peak_start_time`, `peak_end_time`, and `peak_name` have published
  meanings, so reading them is not an inference.

Ordifile still does not integrate the chromatogram. Peaks are the values the file
already carries.

## Container

The reader parses netCDF-3 classic (version 1) and 64-bit-offset (version 2)
headers directly, with no new dependency. Every declared extent is checked against
the file size before it is used, and names, dimension counts, variable counts, and
element counts are all bounded.

Files that declare records are refused with
`NETCDF3_RECORD_VARIABLES_UNSUPPORTED`: record values interleave on disk and no
observed chromatography file uses them. A zero-length dimension is read as an empty
one, which is how writers spell "this file stores no peaks".

## Time axis

The axis is rebuilt as `actual_delay_time + index * actual_sampling_interval`, then
converted to minutes.

That reconstruction is only valid on a uniform grid, so the `ordinate_values`
variable's own declaration is checked: either `uniform_sampling_flag` is `Y` or
`non_uniform_sampling_flag` is `N`. Anything else, including an absent declaration,
fails closed with `ANDI_SAMPLING_NOT_UNIFORM`.

## Retention unit

Writers spell the same unit differently: `time in seconds`, `Seconds`, `Time-Sec`
all appear in the corpus. Only observed spellings are accepted; an unrecognised one
fails closed with `ANDI_RETENTION_UNIT_UNSUPPORTED` rather than being assumed to be
seconds. When the attribute is absent the timing elements are read as seconds,
which is what ASTM E1947 defines them to be, and the decision is reported through
`retention_unit_status` and the `ANDI_RETENTION_UNIT_ABSENT` warning.

## Peak heights that were never computed

Some writers emit a peak-height column of all `-1` or all `0` to mean "not
reported". A negative height is not a height, so it is dropped rather than exported.
A zero is a legal number and is preserved as stored, since it cannot be proven to be
a sentinel. Either way, `stored_peak_height_column_populated` records whether the
whole column looks unpopulated, and `ANDI_PEAK_HEIGHT_NOT_REPORTED` is raised.

## Validation

Each stored peak must contain its own retention time when start and end times are
present, and every peak must fall inside the chromatogram's own reconstructed axis;
otherwise the file fails closed with `ANDI_PEAK_TABLE_INVALID`.

## Not claimed

Vendor extension variables in the same file are not interpreted. `peak_amount`,
area and height percentages, asymmetry, and detection codes are not read, because
their meaning depends on the processing method. Mass spectra, ANDI-MS files,
quantitation, acquisition timestamps, and write support are out of scope.
