# CableModelKit Product Baseline — reconstructed alpha

This extension is forward reconstruction on top of the byte-proven CableModelKit Core recovery baseline. It is **not** claimed to be the lost historical `product-baseline` source.

Its engineering purpose is narrow: bind explicit product-geometry parameters to traceable evidence and compile them into Core `BuildRequest` objects without promoting geometry evidence into electrical ratings, standards compliance, manufacturing qualification, or FEM readiness.

## Evidence boundary

Supported evidence classes are manufacturer drawings, manufacturer catalogues, user-supplied dimensions, and synthetic demonstration fixtures. External evidence marked verified must retain a reference; manufacturer drawings additionally require a revision. The package never creates manufacturer facts by inference.

Every `ProductBaseline` is conservative by contract:

- `standards_compliance = "not_assessed"`
- `manufacturing_ready = false`
- `fem_ready = false`

The current example assets are `synthetic_demo` fixtures used only to exercise deterministic contracts and real OCCT export.

## Verification

The byte-proven historical workflow `.github/workflows/product-baseline.yml` remains the acceptance gate. It checks committed JSON Schemas, compiles the Python surface, executes evidence/preview/geometry/export tests, and builds audited example artifacts using the fixed Core OCCT stack.
