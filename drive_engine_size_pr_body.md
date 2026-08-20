## Summary

This patch adds a normalized `drive` filter to the existing Gemini car-query plan and frontend JACC row matcher. Explicit `2WD`, `2X4`, `4WD`, `4X4`, and `AWD` requests normalize to `2WD` or `4WD`. A row is included only when its loaded JACC data contains a matching verified drive field (`drive`, `drivetrain`, `driveType`, or `wd`). Unknown-drive rows are excluded from explicit drivetrain queries rather than guessed.

The JACC result table now displays a Drive column. Existing price, location, year, chassis, session, quota, and member flows remain unchanged. This does not change Members sheet columns A–I or Apps Script.

The Gemini vehicle-spec prompt now prioritizes engine capacity such as `1.8L / 1,800cc` and `2.0L / 1,998cc`. Power, PS, HP, and torque fields are intentionally omitted from the vehicle-spec response. Gearbox, drive, fuel, and other fields remain source-backed and are shown only when grounding provides them. Gemini payment-slip OCR and auction-photo analysis are untouched.

## Important data boundary

If the car-data API does not provide a drive/drivetrain column, the system will not claim that a row is 2WD or 4WD. The data source must expose a verified drive field for precise Wish 2010 2WD/4WD filtering.

## Validation

Python syntax, HTML structure, inline JavaScript, architecture contracts, drive normalization, invalid-drive rejection, engine-size-only parsing, and the full Phase 1 regression suite pass: **117 passed**, one existing warning.
