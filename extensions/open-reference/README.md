# CableModelKit Open Reference — reconstructed alpha

This package is forward reconstruction guided by the byte-proven historical `open-reference` workflow. It is **not** claimed to be the lost historical implementation.

Its responsibility is evidence discipline, not source scraping: a public document may contribute geometry parameters only when its locator, redistribution license and exact parameter-leaf coverage are explicit. Accessibility alone does not make a source technically authoritative.

## Contract

An `OpenReferenceRecord` binds:

- one CableModelKit `plugin_id`,
- explicit geometry parameters,
- one or more public sources with license metadata,
- every scalar/list parameter leaf to at least one source via JSON Pointer,
- assumptions and conservative qualification flags.

Compilation produces a `ProductBaseline` whose evidence type is `public_reference`. Because the exact Core 0.2.1 provenance enum predates that evidence type, Core build requests are intentionally mapped to `user_dimensions`; the complete source/license metadata stays in the upper-layer baseline rather than being misrepresented as a manufacturer drawing.

All records retain:

- `standards_compliance = "not_assessed"`
- `manufacturing_ready = false`
- `fem_ready = false`

The package contains no fabricated manufacturer catalogue and makes no claim that a public reference is suitable for a particular installation, voltage class, thermal calculation or certified design.
