# CableModelKit Topology Conformity — reconstructed alpha

`topology-conformity` is the first reconstructed layer allowed to change the topology claim. It consumes only an engineering-gate-passed CableModelKit bundle whose Core topology is still `coincident-unmerged`.

The package imports every material-domain B-rep into Gmsh/OpenCASCADE, runs `BooleanFragments`, maps the resulting volumes back to the original stable domain IDs, and then proves each declared neighboring interface has:

- at least one identical shared 2-D geometric entity,
- mesh nodes on that shared surface,
- the same interface nodes present in both neighboring 3-D volume meshes.

Only after those checks pass does the report set:

- `output_topology = "fragmented-shared"`
- `conformal_shared_topology = true`

The emitted mesh remains Gmsh MSH 4.1 in millimeters, matching the Core B-rep coordinate convention.

## What this does not prove

Topology conformity is necessary for many multi-domain FEM workflows, but it is not sufficient for an engineering simulation. A passing topology report still retains:

- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`

Material constitutive data, unit conversion into a solver model, boundary/initial conditions, mesh adequacy for a specific PDE, solver formulation and convergence, and standards validation remain separate gates.
