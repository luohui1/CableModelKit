# Native mesh qualification lab

This directory holds the reproducible engineering fixture used by the native Gmsh qualification gates.

The current evidence chain distinguishes three independent claims:

1. **Simulation preparation** meshes each coincident-unmerged material domain in isolation, then copies the resulting tetrahedral meshes into one discrete aggregate model with stable Physical Groups. Duplicate interface nodes are intentionally retained.
2. **Geometric mesh screening** independently re-reads that aggregate MSH 4.1 file and fails closed on missing domain labels, invalid connectivity, non-finite coordinates, zero-length edges, or degenerate tetrahedra.
3. **Topology conformity** applies OpenCASCADE BooleanFragments, generates a single-threaded HXT mesh, and proves that every declared adjacent material pair shares interface surfaces and mesh nodes.

All coordinates remain in millimetres. These gates do **not** qualify SI conversion, material constitutive data, PDE definitions, boundary conditions, solver convergence, standards compliance, or production FEM readiness. Until those downstream contracts are proven, `fem_ready`, `simulation_ready`, and `manufacturing_ready` remain `false`.
