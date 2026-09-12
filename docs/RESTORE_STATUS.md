# CableModelKit restore status

This document records the repository reconstruction state so that bootstrap data is not mistaken for the final source tree.

## Target state

- Target commit: `c91b0b6` (`feat: add public reference benchmark factory`)
- Target branch: `engineering/reference-factory-0.7a2`
- Target tag: `reference-factory-v0.7.0a2`
- Original tracked files: 592
- Full Git history was previously preserved in a bundle

## Current remote state

The new public repository currently contains an encoded bootstrap source archive under `.bootstrap/source/`.

Observed archive segments on `main`:

- `chunk-00` → original segment 00
- `chunk-01` → original segment 01
- `chunk-02` → original segment 02
- `chunk-03` → original segment 03
- `chunk-08` → original segment 08
- `chunk-09` → grouped restore payload for original segments 09–11
- `chunk-12` → grouped restore payload for original segments 12–14
- `chunk-15` → grouped restore payload for original segments 15–17
- `chunk-18` → grouped restore payload for original segments 18–20
- `chunk-21` → grouped restore payload for original segments 21–23
- `chunk-24` → grouped restore payload for original segments 24–26

The commit messages confirm the grouped restore pattern for the later payloads.

## Missing payload

Original bootstrap segments **04–07** are not present in the current Git tree or reachable commit history.

Because the staged source data is an encoded/compressed archive, reconstructing the final 592-file source tree before recovering these missing segments would risk producing corrupted or incomplete source. For that reason, the bootstrap payload must remain untouched until all segments are available.

## Recovery rules

1. Do not delete or rewrite `.bootstrap/source/*` until archive verification succeeds.
2. Do not recreate the missing segments from guesses or generated code.
3. Recover segments 04–07 from the preserved bundle/source package or another verified copy.
4. Concatenate/decode the complete bootstrap payload using the original archive procedure.
5. Verify file count, checksums where available, branch state and target commit identity.
6. Restore the formal source tree.
7. Restore the `reference-factory-v0.7.0a2` tag only after verification.
8. Run repository tests/CI before declaring the public recovery complete.

## Current branch policy

`main` remains the bootstrap/recovery baseline. Active reconstruction and documentation work proceeds on `engineering/reference-factory-0.7a2` until the restored source is verified.
