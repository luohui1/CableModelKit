# CableModelKit Section Profile — reconstructed alpha

`section-profile` is a forward-reconstructed geometry extension for explicit cross-section domain identity. It is new implementation constrained by the surviving CableModelKit plugin contract and engineering-gate workflow; it is **not** presented as recovered historical source.

## Scope

The `cable.section_profile` plugin accepts a straight concentric radial profile and produces one independent OCCT solid per declared domain. Each domain carries:

- a stable domain ID,
- a role and material reference,
- an analytic expected volume,
- an independent B-rep/STEP-exportable solid,
- explicit logical interfaces to adjacent radial domains.

The domain radii must be strictly increasing. Adjacent solids are coincident at their cylindrical boundary but intentionally remain unmerged so downstream meshing and field-mapping layers can decide how to construct shared topology.

## Acceptance fixture

`examples/profiled-19.json` is a **synthetic 22-domain stress fixture** used by the reconstructed engineering gate. The split layers are intentionally detailed to exercise domain preservation; they are not manufacturer construction data and should not be read as a recommended cable design.

## Qualification boundary

This extension proves geometry segmentation only. It does not by itself establish:

- FEM readiness or conformal mesh quality,
- thermal/electrical material properties,
- strand or armour-wire discreteness,
- manufacturing tolerances,
- standards compliance,
- manufacturer approval.

Those concerns belong to later qualification layers and must remain explicit.
