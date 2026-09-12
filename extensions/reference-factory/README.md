# CableModelKit Reference Factory — reconstructed alpha

This package is forward reconstruction guided by the byte-proven historical `reference-factory` workflow and the historical target description `feat: add public reference benchmark factory`. It is **not** claimed to be the lost historical implementation.

The factory has two deliberately separate responsibilities:

1. compile deterministic, CAD-free reference release records whose provenance and qualification boundaries can be audited without loading OCCT or Gmsh;
2. expose an optional pinned native Gmsh smoke path proving that named physical groups can be emitted into a real `.msh` file.

## Default release policy

`cmk-reference-factory compile OUTPUT` currently emits only three `synthetic_demo` geometry benchmarks: round cable, equal-core multicore cable, and duct bank. This is intentional. No manufacturer dimensions, public catalogue facts or standards claims are fabricated to make the release appear fuller than the available evidence.

The release manifest therefore records:

- `default_record_policy = "synthetic_only"`
- `license_status = "project_owner_decision_pending"`
- `standards_compliance = "not_assessed"`
- `manufacturing_ready = false`
- `fem_ready = false`

Public-reference records can be introduced only through the reconstructed `open-reference` evidence layer, where source locator, redistribution license and parameter-leaf evidence coverage are explicit.

## Determinism

Every record is serialized deterministically, hashed with SHA-256, listed in `release/public-reference-v0.1.json`, and revalidated against the current Core plugin contract by `cmk-reference-factory verify-release OUTPUT`.

The compiler refuses to overwrite an existing release directory and stages output transactionally before renaming it into place.

## Native Gmsh smoke

`cmk-reference-factory gmsh-smoke model.msh` generates a synthetic 2-D concentric two-region mesh with exactly these physical group names:

- `region/conductor`
- `region/insulation`
- `interface/conductor_insulation`
- `boundary/outer`

The sidecar `model.msh.json` explicitly remains `fem_ready=false`. Physical-group existence proves only native Gmsh/runtime and naming plumbing; it does not establish real material physics, solver boundary conditions, mesh convergence, standards compliance or simulation readiness.
