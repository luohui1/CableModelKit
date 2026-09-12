# CableModelKit thermal tetra solver — reference alpha

This extension assembles and solves the complete three-dimensional linear-tetrahedral weak form for the retained conformal radial thermal benchmark.

It consumes the output of `cable-modelkit-thermal-contract`, converts the MSH 4.1 millimetre coordinates to SI metres, maps each tetrahedral volume entity to its thermal conductivity and volumetric source, reconstructs the exterior triangular facets, applies the retained outer convection condition, and solves the sparse system with SciPy SuperLU.

## Numerical evidence

A solve bundle retains:

- the source thermal contract, benchmark specification, topology report and mesh;
- an immutable solve request;
- full nodal numerical and analytic temperatures;
- domain element/volume/source summaries;
- matrix dimensions and nonzero count;
- maximum nodal temperature error and normalized RMS error;
- generated-versus-convected energy balance;
- sparse linear residual;
- implementation and SciPy identities.

The convergence command accepts independently retained meshes rebuilt at decreasing topology mesh-size scales. It checks strictly increasing node/element counts, decreasing actual maximum tetrahedral edge, strictly decreasing maximum temperature error, observed order, Richardson extrapolation and fine-grid GCI.

## Commands

```bash
cable-modelkit-thermal-tetra solve \
  out/thermal-contract \
  out/tetra-solver \
  --max-temperature-error-k 0.1 \
  --max-energy-balance-error 1e-8 \
  --max-linear-residual 1e-8

cable-modelkit-thermal-tetra verify out/tetra-solver

cable-modelkit-thermal-tetra converge \
  thermal_lab/tetra-convergence-plan.json \
  out/tetra-convergence \
  out/tetra-coarse out/tetra-medium out/tetra-fine

cable-modelkit-thermal-tetra verify-convergence out/tetra-convergence
```

## CI gate

The repository gate rebuilds one engineering source into three conformal HXT meshes, prepares an independently hashed SI thermal contract for each mesh, solves all levels, recomputes the fine solve during verification, and evaluates retained three-level convergence evidence. Every intermediate geometry, mesh, contract, solution profile and report is uploaded as an Actions artifact.

## Qualification boundary

Passing this extension proves the controlled benchmark on this specific conformal tetrahedral pipeline. Boundary selection is intentionally tied to the concentric benchmark. Synthetic material properties, benchmark geometry and one PDE do not qualify a production cable calculation.

The reports retain:

- `production_solver_adapter_ready = false`
- `production_mesh_convergence_ready = false`
- `project_material_data_ready = false`
- `general_3d_fem_ready = false`
- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`
