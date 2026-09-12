# CableModelKit Simulation Prep — reconstructed alpha

`simulation-prep` is a conservative hand-off layer between an accepted CableModelKit engineering-geometry bundle and later meshing/solver qualification. It is forward-reconstructed code and is **not** claimed to be recovered historical source.

The package accepts only bundles containing both `asset.json` and a passed `gate.json`. It re-validates the source file-integrity map, requires the source topology to remain `coincident-unmerged`, and refuses any source whose engineering gate has silently upgraded FEM, simulation, manufacturing or standards qualification.

## Domain transfer

Every B-rep domain is mapped to a stable Gmsh Physical Group named `domain/<domain-id>`. When `--mesh` is enabled, each B-rep is imported as an independent Gmsh 3-D volume and a coarse plumbing mesh is generated. `--verify-mesh` additionally re-reads the `.msh` file with meshio and confirms the expected Physical Groups survived exchange.

This deliberately preserves the current topology boundary: **independent imported volumes are not proof of conformal shared topology**. Coincident interfaces can therefore carry duplicate faces/nodes until a later topology/mesh layer explicitly fragments/imprints and verifies them.

## Qualification boundary

A prepared bundle always keeps:

- `conformal_shared_topology = false`
- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`

Physical Group coverage proves domain identity transfer only. It does not prove element quality, material constitutive properties, boundary conditions, solver convergence, thermal/electrical validity, or standards compliance.
