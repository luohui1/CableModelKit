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

## Forensic run 2026-09-12

GitHub Actions run `34667320962` executed `tools/bootstrap_forensics.py` successfully on Python 3.13.

Verified findings:

- `chunk-00` through `chunk-03` form a contiguous, valid Base64/GZip prefix.
- The prefix decodes to 18,000 compressed bytes and inflates to 74,580 bytes of TAR data.
- 29 TAR entries are identifiable before the gap; 23 regular files are fully complete and byte-recoverable.
- The last fully complete source file is `src/cable_modelkit/plugins/infrastructure.py`.
- `src/cable_modelkit/plugins/duct_bank.py` begins in the proven prefix but is truncated by the missing compressed region and must not be restored as a complete file.
- Logical segments **04–07** are missing, corresponding to 24,000 Base64 characters / 18,000 decoded compressed bytes under the established chunk convention.
- `chunk-12` contains 17,996 Base64 characters although the 12→15 span convention calls for 18,000. This is a second independent anomaly: four Base64 characters (approximately three compressed bytes) are absent relative to the nominal grouping pattern.
- Full archive restoration is therefore not currently safe.

The forensic report was uploaded by the workflow as artifact `bootstrap-forensics` (artifact id `10289703105`).

## Proven complete prefix files

The forensic parser established the following complete prefix boundary:

- repository workflows through `reference-factory.yml`
- `CONTRIBUTING.md`
- `.gitattributes`
- `LICENSE_STATUS.md`
- `pyproject.toml`
- original `README.md`
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

The workflow inventory is authoritative for exact entry boundaries; no incomplete entry is promoted as recovered source.

## Recovery policy

1. Never delete or rewrite `.bootstrap/source/*` on `main` until archive recovery is closed.
2. Never recreate missing compressed bytes or source files from guesses and label them historical source.
3. Recover all byte-provable complete files on a dedicated `recovery/proven-prefix` branch.
4. Keep incomplete `duct_bank.py` out of the restored source tree.
5. Continue searching for original segments 04–07 and the missing `chunk-12` tail bytes in preserved bundles, old workspaces or verified copies.
6. Any best-effort DEFLATE resynchronization of the suffix must live in forensic tooling/output and must not be presented as exact source until file-level integrity is proven.
7. Restore `reference-factory-v0.7.0a2` only after the target source state and commit identity are verified.
8. Run the repository's recovered tests/CI before declaring the public recovery complete.

## Branch policy

- `main`: immutable bootstrap/recovery evidence baseline for now.
- `engineering/reference-factory-0.7a2`: recovery tooling, documentation and continued engineering work.
- `recovery/proven-prefix`: byte-exact files extracted from the verified contiguous archive prefix only.
