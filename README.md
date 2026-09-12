# CableModelKit

CableModelKit is the modeling subsystem and plugin foundation for the CableSimPro ecosystem.

Its target is an engineering-grade, parameter-driven cable modeling stack rather than a visualization-only demo. The repository is intended to contain the modeling core, plugin integration layer, engineering schemas, reference assets, validation tests and documentation required to generate reusable model artifacts for CableSimPro and downstream reporting/analysis workflows.

## Scope

- Parametric cable geometry generation
- Engineering material and layer definitions
- Reference cable structures and benchmark assets
- Cable / material / model-artifact schemas
- Plugin capability contracts for CableSimPro
- 2D section, 3D model and engineering-view outputs
- Deterministic validation and regression tests

## Repository state

The original development state is currently being restored into this newly created public repository.

Target recovery point:

- Commit: `c91b0b6` — `feat: add public reference benchmark factory`
- Development branch: `engineering/reference-factory-0.7a2`
- Version tag: `reference-factory-v0.7.0a2`
- Original tracked files: 592

The bootstrap source archive is only partially staged at the moment. Do not treat `main` as a completed source release until recovery verification is finished. See `docs/RESTORE_STATUS.md` on the development branch for the exact recovery state.

## Planned layout

```text
CableModelKit/
├── plugin/              # CableSimPro modeling plugin integration
├── modeling/            # Parametric modeling core
├── reference-assets/    # Reference cable structures and engineering assets
├── schemas/             # Cable, material and model-artifact schemas
├── tests/               # Geometry, schema and regression validation
├── docs/                # Architecture and engineering documentation
└── .github/workflows/   # CI and validation workflows
```

## Relationship to CableSimPro

CableSimPro is the host engineering application. CableModelKit is designed to provide reusable modeling capabilities through explicit schemas and plugin contracts, without duplicating the host application's project state or solver responsibilities.

> Recovery in progress. Engineering claims and release tags will only be restored after the source tree and Git history are verified.
