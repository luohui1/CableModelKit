# CableModelKit Thermal Contract — reconstructed alpha

This extension converts a retained `topology-conformity` bundle into a self-contained, solver-neutral steady-thermal contract for the controlled concentric-cylinder benchmark.

It proves the next contract layer only:

- the source MSH 4.1 coordinates are millimetres and the solver length scale is explicitly `0.001 m/mm`;
- every conformal volume Physical Group receives exactly one thermal material assignment;
- every conductivity value has machine-readable provenance and a validity interval;
- the strong-form PDE is `-div(k*grad(T)) = q_v` with temperature and normal-flux continuity at shared interfaces;
- the outer cylindrical surface is selected from retained MSH entity ownership/bounding boxes and receives convection;
- all remaining external end surfaces receive the natural zero-normal-flux policy;
- a closed-form multilayer radial solution balances generated and convected heat.

The included material values are deliberately synthetic benchmark controls. They are not manufacturer values, cable ratings, or project-qualified constitutive data. The package therefore retains:

- `project_material_data_ready = false`
- `solver_adapter_ready = false`
- `mesh_convergence_ready = false`
- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`

The next layer must bind this contract to an independently verified numerical solver and demonstrate convergence to the analytic temperature field before any FEM-readiness claim can change.
