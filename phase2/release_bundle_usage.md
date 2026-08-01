# JACC Phase 2 release-candidate bundle

Status: staged only. Building the ZIP does not deploy production.

## Inputs

Export the current Apps Script project files without changing them:

- `Code.gs`
- `Payment.gs`
- `Registration.gs`
- `Phase3Payments.gs`

Keep these private. The builder records only SHA-256 input hashes in the ZIP
manifest and does not include the unmodified sources.

## Command

```bash
python phase2/build_release_candidate_bundle.py \
  --code /private/current/Code.gs \
  --payment /private/current/Payment.gs \
  --registration /private/current/Registration.gs \
  --phase3 /private/current/Phase3Payments.gs \
  --output /private/JACC_Phase2_Release_Candidate.zip
```

The builder:

1. applies all four guarded transformers;
2. refuses unknown source drift;
3. adds the seven Phase 2 Apps Script modules;
4. adds the generated website and Railway Phase 2 runtime files;
5. scans the complete candidate for literal credentials;
6. writes file sizes and SHA-256 checksums to `manifest.json`;
7. creates a deterministic review-only ZIP.

## Required review

Before deployment, extract the ZIP and manually compare:

- `AppsScript/Code.gs`
- `AppsScript/Payment.gs`
- `AppsScript/Registration.gs`
- `AppsScript/Phase3Payments.gs`

against the current Apps Script project. Do not paste a partial set of files.

The ZIP must not contain values for `JACC_SERVER_KEY`, `SHEET_SERVER_KEY`, or
`BOT_TOKEN`. Set those only in Apps Script Script Properties and Railway
Variables during the coordinated maintenance window.

## Production boundary

The ZIP is not approval to deploy. Apps Script, Railway, and Website must be
activated atomically, followed by the complete live acceptance matrix and
explicit owner approval before PR #12 is marked Ready or merged.
