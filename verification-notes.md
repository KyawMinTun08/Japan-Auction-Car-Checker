# JACC chassis specification verification notes

- Current live page and local preview both load the existing JACC login/dashboard shell.
- The Android and Flutter app folders are WebView wrappers around the GitHub Pages site, so website UI changes are inherited by both app shells.
- The new `vehicle-specs.js` asset is referenced by `index.html`; `sw.js` includes it in the app shell and uses cache version `2026.08.14-chassis-spec.1`.
- Browser visual verification is being performed against the local preview URL; login/data loading is intentionally not attempted because it would require a real Premium session and live Google Sheets credentials.

## Browser render result

The local preview rendered `AGH30-0015779` into a complete `vehicle-spec-card` with the expected fields: Generation, Chassis, Engine, Engine Size, Engine Type, Drive, Gearbox, Power, Torque, Fuel, Fuel Tank, and Seats. The card also displayed Burmese explanation text, inspection reminders, reference links, and an auction-record-not-found note. The preview screenshot showed the card inside the existing Chassis Lookup page without breaking the sidebar or search controls.

## Existing record preservation test

A second browser test injected a representative Sheet record for `AGH30-0015779`. The result contained both the new specification card and the existing auction record card, including the Sheet chassis, model, year, location, and price. The test returned `specCard: true`, `hasPrice: true`, and the existing record header text.
