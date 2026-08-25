# Ordifile documentation

Start with the path that matches your task.

## Researcher workflow

1. [Install and run the public-safe pilot](user/pilot-checklist.md).
2. Check [supported formats and exact profile boundaries](../README.md#verified-formats).
3. Prepare generic tables with the [generic tabular schema](formats/generic-tabular.md).
4. Map unfamiliar Result tables and reuse templates with
   [Mapping Profiles, Mapping Sets, drift repair, Preflight, and Recipes](formats/explicit-peak-table-mapping.md).
5. Review the [workbook interpretation guide](user/workbook-guide.md).
6. Submit privacy-safe [pilot feedback](https://github.com/hdkim99/ordifile/issues/new/choose)
   or a [format support request](https://github.com/hdkim99/ordifile/issues/new/choose).

The short product boundary is in [Product concept](product-concept.md). Exact
Experimental profile support, generic user mapping, research blocked by missing fixture
evidence, and unsupported inputs are separate states.

## Contributors and maintainers

- [Fixture intake](contributing/result-fixture-intake.md)
- [Researcher acceptance suite](contributing/researcher-acceptance.md)
- [Architecture decisions](architecture/decision-record.md)
- [Cross-vendor compatibility and partial-capability policy](architecture/cross-vendor-compatibility-policy.md)
- [Proprietary adapter hard-gate audit](research/cross-vendor-adapter-hard-gate-audit.md)
- [Evidence and source register](research/source-register.md)
- [Release process](releasing.md)
- [Standalone prototype boundary](standalone.md)

Files under `docs/research/` record evidence and unresolved format boundaries. They are
not a promise of format support. Versioned notes under `docs/releases/` are historical
release records; current user instructions live in the README and the researcher guides
above.
