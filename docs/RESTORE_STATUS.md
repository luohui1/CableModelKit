# CableModelKit restore status

This document records the repository reconstruction state so that bootstrap data is not mistaken for the final source tree.

## Target state

- Target commit: `c91b0b6` (`feat: add public reference benchmark factory`)
- Target branch: `engineering/reference-factory-0.7a2`
- Target tag: `reference-factory-v0.7.0a2`
- Original tracked files: 592
- Full Git history was previously preserved in a bundle, but that bundle is not currently available through the connected file/runtime sources

## Verified historical project identity

A deterministic forensic pass over the contiguous bootstrap prefix recovered original repository files and metadata. These are evidence from the archived source stream, not reconstructed guesses.

Verified facts include:

- Python package: `cable-modelkit`
- Core package version: `0.2.1`
- Historical README delivery label: `Professional Suite 0.3.0 / Core 0.2.1`
- Python range: `>=3.11,<3.14`
- Core dependency: `pydantic==2.13.4`
- Optional CAD stack: `cadquery==2.8.0`, `cadquery-ocp==7.9.3.1.1`
- Test/tooling dependencies include pytest, Ruff, jsonschema and trimesh
- Recovered workflows prove OCCT/CadQuery and Gmsh-based engineering validation were part of the repository design
- The package is headless and independent of CableSimPro; it exposes engineering geometry/plugin capabilities rather than a host UI, solver or network service

## Current remote bootstrap state

The public repository contains an encoded bootstrap source archive under `.bootstrap/source/`.

Observed archive segments on `main`:

- `chunk-00` → logical segment 00
- `chunk-01` → logical segment 01
- `chunk-02` → logical segment 02
- `chunk-03` → logical segment 03
- `chunk-08` → logical segment 08
- `chunk-09` → grouped payload for logical segments 09–11
- `chunk-12` → grouped payload intended for logical segments 12–14
- `chunk-15` → grouped payload for logical segments 15–17
- `chunk-18` → grouped payload for logical segments 18–20
- `chunk-21` → grouped payload for logical segments 21–23
- `chunk-24` → final grouped payload beginning at logical segment 24

The commit chain proves `chunk-08` was committed directly after `chunk-03`; segments 04–07 were never present in this remote history.

## Exact prefix recovery

GitHub Actions run `34667320962` executed `tools/bootstrap_forensics.py` successfully on Python 3.13.

Verified findings:

- `chunk-00` through `chunk-03` form a contiguous, valid Base64/GZip prefix.
- The prefix decodes to 18,000 compressed bytes and inflates to 74,580 bytes of TAR data.
- 29 TAR entries are identifiable before the gap; 23 regular files are fully complete and byte-recoverable.
- The last fully complete source file is `src/cable_modelkit/plugins/infrastructure.py`.
- `src/cable_modelkit/plugins/duct_bank.py` begins after that boundary but cannot be promoted as exact historical source.
- Logical segments **04–07** are missing, corresponding to 24,000 Base64 characters / 18,000 decoded compressed bytes under the established chunk convention.
- `chunk-12` contains 17,996 Base64 characters although the 12→15 span convention calls for 18,000. This is a second independent anomaly: four Base64 characters (approximately three compressed bytes) are absent relative to the nominal grouping pattern.
- Full archive restoration is therefore not currently safe.

The exact prefix has been materialized on `recovery/proven-prefix`. Historical workflow files were promoted using their original Git blob objects rather than rewritten through CI.

## Proven complete prefix files

The forensic parser established the following complete regular files:

- `.github/workflows/open-reference.yml`
- `.github/workflows/engineering-gate.yml`
- `.github/workflows/runtime-link.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/mesh-quality.yml`
- `.github/workflows/mesh-bridge.yml`
- `.github/workflows/product-baseline.yml`
- `.github/workflows/reference-factory.yml`
- `CONTRIBUTING.md`
- `.gitattributes`
- `LICENSE_STATUS.md`
- `pyproject.toml`
- `README.md`
- `SECURITY.md`
- `src/cable_modelkit/py.typed`
- `src/cable_modelkit/__init__.py`
- `src/cable_modelkit/gltf.py`
- `src/cable_modelkit/schema.py`
- `src/cable_modelkit/engine.py`
- `src/cable_modelkit/exporters.py`
- `src/cable_modelkit/errors.py`
- `src/cable_modelkit/plugins/__init__.py`
- `src/cable_modelkit/plugins/infrastructure.py`

The manifest on `recovery/proven-prefix` is authoritative for exact sizes and SHA-256 values. No incomplete entry is included in that exact baseline.

## Suffix recovery investigation

The surviving chunks were also assembled into a damaged gzip stream without inserting synthetic padding. This stream is 101,700 bytes and has SHA-256 `3e882f0e2d9cf3ee95f4dedb0e20ec095304e618608a48638355067dac04d836`.

### gzrecover and gztool

GitHub Actions suffix-forensics runs tested two independent recovery implementations:

- `gzrecover 0.8`
- `gztool 1.6.1` in patch mode

Both produced exactly 473,488 bytes of decompressed output with SHA-256 `9c1d34c341b76e4ecb14ee995f0f606493fc1bc82ee6ef4a91d0d09493ce3889`.

Both outputs contain the same 29 valid USTAR headers and the same 28 header+payload+next-header chains, all belonging to the already proven prefix. Neither tool found a new valid TAR chain after the damaged region.

`src/cable_modelkit/plugins/duct_bank.py` is visible as a candidate TAR member with size 2,409 bytes and payload SHA-256 `4d39481fc5ff13242290cff5e5fe6068bfda188c871e2cbbe98a89c111ef0bae`, but its expected next TAR header is invalid. Because the recovered bytes may be influenced by damaged DEFLATE history, this file is **not** classified as byte-exact historical source and is not promoted to `recovery/proven-prefix`.

### Raw DEFLATE resynchronization probe

A conservative probe then scanned the fully contiguous post-anomaly compressed suffix:

- source chunks: `chunk-15`, `chunk-18`, `chunk-21`, `chunk-24`
- compressed bytes: 52,203
- SHA-256: `ff6fcecf556639d3949e1618fe798b85c736a3883bb6e72fbefdc89d82e54f2b`

The probe tested all eight possible bit phases and all byte starts as potential raw-DEFLATE block boundaries. Each potential start was decompressed with three deliberately different 32 KiB preset dictionaries. A candidate required long decompressed output, at least a 32 KiB dictionary-independent common suffix, and structurally valid TAR headers inside that converged region.

Result: **0 candidates**.

This does not constitute a mathematical proof that no specialist forensic technique could ever recover additional bytes, but together with the two standard recovery tools it closes the practical direct-resynchronization routes against the current remote evidence.

Latest suffix-forensics run: `34667954296`.
Latest suffix-forensics artifact: `10289589181`.

## Current recovery boundary

The exact historical recovery boundary remains **23 complete files** ending at `src/cable_modelkit/plugins/infrastructure.py`.

No additional source file after that boundary has met the repository's byte-exact promotion standard.

Exact completion of the historical 592-file tree now requires at least one external verified source not currently available here, such as:

- original logical segments 04–07,
- the missing tail of logical 12–14,
- the previously preserved Git bundle,
- an old workspace/clone containing commit `c91b0b6`, or
- another independently verifiable copy of the original repository.

## Engineering continuation policy

Recovery and forward engineering are now separated explicitly:

1. `main` remains the bootstrap evidence baseline and must not be rewritten while recovery is open.
2. `recovery/proven-prefix` contains only byte-exact recovered historical files.
3. `engineering/reference-factory-0.7a2` contains forensic tooling, documentation and recovery experiments.
4. Forward reconstruction must occur on a separately named reconstruction branch derived from `recovery/proven-prefix`.
5. Any newly implemented file is labeled reconstructed/new work and must never be represented as the original historical bytes.
6. Reconstructed behavior should use the exact README, package metadata, workflow contracts, schemas and surviving APIs as acceptance evidence.
7. The historical tag `reference-factory-v0.7.0a2` must not be recreated until the historical target itself is verified.

## Next engineering objective

With direct byte recovery exhausted to a strong practical level, the next productive step is provenance-preserving reconstruction of the missing engineering surface. Priority is driven by the recovered historical CI contracts:

1. complete the missing Core/plugin API surface needed by the package CLI and build flows;
2. restore a working `product-baseline` extension contract;
3. restore `open-reference`;
4. restore `reference-factory` and its Gmsh verification path;
5. restore validation scripts/tests and then expand to the remaining engineering extensions.

Each reconstructed subsystem must earn its way forward through the recovered historical workflows or equivalent explicit tests.
