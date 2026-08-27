# Cross-vendor automatic Result acquisition evidence

- Reviewed: 2026-08-26
- Product version: v0.5.1; next version unresolved
- Scope: official local Result acquisition feasibility, not scientific inference

## Evidence decision matrix

| Vendor/source | Direct capability | Existing exact Result path | Automatic acquisition decision | Reason |
|---|---|---|---|---|
| YoungIn YL-Clarity PRM | validated scientific FID/TCD Signals for the supported family | exact YL-Clarity Result Table CSV adapter | `PILOT_REQUIRED` | documented command path and strong paired data exist; actual licensed Windows unattended behavior and export-profile stability are not yet executed |
| Agilent ChemStation CH | structural records | exact ChemStation Result XML adapter | `FEASIBILITY_ONLY` | official XML Result export exists, but one `.CH` may require its `.D` run and method/result context; no same-run automated replay evidence |
| Shimadzu GCD/QGD | GCD signal; QGD RT/TIC with unresolved physical TIC unit | exact Result ASCII adapter for its validated profile | `FEASIBILITY_ONLY` | official integration/linkage products exist, but no documented exact on-demand native-file replay to the supported grammar was established |
| LECO ChromaTOF Result TXT | direct RT1/RT2/Area/Height Peaks | same source is already the Result | `NOT_NEEDED` | no lawful native-source workflow has been supplied |

No production provider is registered. Direct parsers and user-supplied Result adapters remain
unchanged.

## Owner-controlled YoungIn evidence

The local-only corpus already performs the comparison requested for direct scientific decoding:

- twelve exact 9.0.1.19 FID+TCD PRM/full-curve pairs compare 316,220 time points and 316,220 signal
  points;
- five exact 9.1.0.76 FID+TCD pairs compare 138,000 time points and 138,000 signal points;
- all 454,220 points match the official exports under their printed precision contract;
- the same-run curves establish the shared zero-origin `DStep/MinTicks` minute axis and identity
  numeric response, with profile-specific response units;
- paired composite exports provide 347 Result rows as local-only development oracles, but no
  repeatable stored PRM RT/Area/Height table was identified. They do not license automatic
  peak detection or a claim of vendor-equivalent Area.

This evidence is sufficient for the existing direct Signals implementation. It is also sufficient
to test exact Result parsing and logical-source merge. It is not evidence that invoking a local
YL-Clarity executable is unattended, deterministic, or uses the expected active export profile.

## Official references

YoungIn/DataApex:

- [Clarity command-line parameters](https://www.dataapex.com/documentation/Content/Help/110-technical-specifications/110.020-command-line-parameters/110.020-command-line-parameters.htm)
- [Export Results workflow](https://www.dataapex.com/documentation/Content/lims/020-workflows-in-clarity/020-070-export-results.htm)
- [Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
- [All Signals Results](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-all-signals-results.htm)
- [YL-Clarity product page](https://eng.youngincm.com/goods/read.php?M2_IDX=18459&SC_BOOKMARK=N&SC_SC1_IDX=404&SC_SC2_IDX=1082&SC_SF_IDX=Array&SP_CODE=19113EE3)

Agilent:

- [ChemStation XML Connectivity Guide](https://www.agilent.com/Library/usermanuals/Public/CDS_CS_XML.pdf)
- [Understanding Your ChemStation](https://www.agilent.com/cs/library/usermanuals/Public/G2070-91126_Understanding.pdf)

Shimadzu:

- [LabSolutions Sync](https://www.shimadzu.com/an/products/software-informatics/labsolutions-sync/features.html)
- [LabSolutions System Linkage Option](https://www.shimadzu.com/an/products/software-informatics/labsolutions-series/system-linkage-option/features.html)
- [Software license management](https://www.shimadzu.com/an/service-support/software-license-management/index.html)

LECO:

- [ChromaTOF GC legacy documentation](https://www.leco.com/documents/chromatof-gc-legacy-version/)

Vendor names identify compatibility targets only. Ordifile is independent and bundles no vendor
software, DLL, source, credentials, or private fixture bytes.
