# CableModelKit Mesh Quality — reconstructed alpha

`mesh-quality` performs a narrow, fail-closed **geometric mesh screening** on the output of `simulation-prep`. It is forward-reconstructed code and is not presented as recovered historical source.

The analyzer independently re-reads the prepared Gmsh file with meshio and checks:

- the file bytes actually declare Gmsh MSH 4.1,
- the upstream unit contract is explicitly millimeters,
- every expected 3-D Physical Group exists and contains tetrahedra,
- tetrahedral connectivity references valid finite points,
- no tetrahedron has a zero-length edge,
- no tetrahedron is degenerate under a scale-independent normalized-volume test,
- element counts agree with the upstream preparation evidence.

It also records descriptive tetrahedron volume and edge-ratio statistics. Those statistics are evidence for later solver-specific qualification; they are **not** treated as universal production thresholds.

## Why FEM-ready remains false

The current preparation stage imports material domains independently. It has not yet proven conformal shared topology across coincident interfaces. Therefore even a mesh that passes all geometric screening retains:

- `conformal_shared_topology = false`
- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`

A later qualification layer must explicitly prove topology conformity, material-property completeness, boundary-condition validity, solver setup/convergence and problem-specific mesh adequacy before those claims can change.
