# CableModelKit Engineering Gate — reconstructed alpha

`engineering-gate` is a forward-reconstructed acceptance layer above CableModelKit Core. It is new implementation constrained by the surviving `engineering-gate.yml` workflow and the Core 0.2.1 artifact contract; it is **not** claimed to reproduce lost historical source.

Its purpose is to answer a narrow question: **does an explicit multi-domain CAD model preserve its domain identity and basic geometric integrity through independent exchange?**

## Checks

For a build request, the gate:

- builds the model through the normal CableModelKit plugin API,
- scans every domain pair for non-zero material-volume overlap,
- exports the normal transactional CableModelKit bundle,
- re-hashes every file recorded by `asset.json`,
- independently re-imports STEP and checks solid count and total volume,
- independently re-imports GLB when requested and checks domain geometry count,
- writes `gate.json` only after every acceptance check passes.

Coincident zero-volume boundary faces are allowed. Core 0.2.x deliberately exports `coincident-unmerged` topology, so this gate does not pretend that shared/conformal topology already exists.

## 22-domain acceptance fixture

The surviving workflow names `extensions/section-profile/examples/profiled-19.json` as its acceptance model. In the reconstruction that file is an explicitly synthetic **22-domain** radial stress fixture. Passing it proves that 22 named OCCT solids survive the scoped gate; it does not make that synthetic layer stack a real product construction.

## Qualification boundary

A passing report retains all of the following:

- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`

The gate does **not** establish conformal meshing, element quality, material constitutive data, solver validity, thermal/electrical boundary conditions, manufacturing tolerances, or standards compliance. Those are separate downstream qualification layers.
