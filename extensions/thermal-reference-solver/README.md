# CableModelKit thermal reference solver

This extension adds a deterministic **one-dimensional axisymmetric linear Galerkin FEM** for the controlled radial thermal benchmark emitted by `cable-modelkit-thermal-contract`.

It is an independent numerical cross-check of the solver-neutral contract. It is not a general three-dimensional FEM engine and does not qualify manufacturer data, production cable ratings, standards compliance, or ampacity.

## Numerical model

For each radial element, the implementation assembles the weak form of

\[
-\frac{1}{r}\frac{d}{dr}\left(r k \frac{dT}{dr}\right)=q_v
\]

with exact radial integration of the linear-element stiffness and source terms. The outer surface uses convection,

\[
-k\frac{dT}{dr}=h(T-T_\infty),
\]

and the centerline uses the natural symmetry condition. The linear tridiagonal system is solved by a deterministic Thomas algorithm using Python binary64 arithmetic.

## Evidence

`solve` emits:

- the copied thermal contract and benchmark specification;
- a full numerical/analytic radial temperature profile;
- implementation SHA-256 identity;
- maximum nodal temperature error;
- normalized radial RMS error;
- generated-versus-convected heat balance;
- explicit reference-only qualification flags.

`converge` executes a constant-ratio refinement plan and emits:

- at least three strictly refined levels;
- observed maximum-error orders;
- observed center-temperature solution order;
- Richardson-extrapolated center temperature;
- fine-grid relative GCI;
- independently reproducible CSV evidence.

## Usage

```bash
python -m pip install -e extensions/thermal-reference-solver

cable-modelkit-thermal-reference solve \
  out/thermal-contract out/reference-solver \
  --cells-per-layer 16,16,16,16 \
  --max-temperature-error-k 0.0001 \
  --max-energy-balance-error 1e-8

cable-modelkit-thermal-reference verify out/reference-solver

cable-modelkit-thermal-reference converge \
  out/thermal-contract \
  thermal_lab/reference-convergence-plan.json \
  out/reference-convergence

cable-modelkit-thermal-reference verify-convergence out/reference-convergence
```

## CI gate

The repository workflow rebuilds the conformal topology and SI thermal contract from source, executes the retained reference solve and four-level refinement plan, independently verifies both bundles, and uploads the complete evidence chain.

## Qualification boundary

Passing this extension proves only that the controlled radial benchmark is reproduced by this specific reference discretization with the retained refinement evidence. The reports intentionally keep:

- `production_solver_adapter_ready = false`
- `production_mesh_convergence_ready = false`
- `general_3d_fem_ready = false`
- `fem_ready = false`
- `simulation_ready = false`
- `manufacturing_ready = false`
- `standards_compliance = "not_assessed"`
