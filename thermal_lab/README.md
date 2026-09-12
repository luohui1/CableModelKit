# Thermal qualification laboratory

The retained benchmark chain is deliberately split into independently auditable claims:

1. `thermal-contract` maps a conformal four-domain radial cable mesh to explicit SI units, constitutive assignments, PDE semantics, boundary sets, and an analytic multilayer-cylinder solution.
2. `thermal-reference-solver` independently assembles and solves a one-dimensional axisymmetric linear Galerkin FEM and compares every radial node with the analytic solution.
3. `reference-convergence-plan.json` drives the fixed-ratio sequence `2 → 4 → 8 → 16` elements per material layer and requires near-second-order convergence, energy balance, Richardson extrapolation, and a fine-grid GCI.

The laboratory uses controlled synthetic material values. It does not represent manufacturer data, standards-based ampacity, a production three-dimensional solver, or general FEM qualification.
