# Hybrid Source-Check Verification

## Local browser test

The local JACC preview was loaded with a representative ALPHARD record (`AGH30-0015779`). The Explorer rendered one vehicle card and exposed one contextual `Japan Source ↗` action. The next verification step is to activate that action and confirm that the Chassis Lookup page receives the normalized selected chassis, retains the existing Sheet record details, and renders the existing source handoff card.

## Explorer action handoff

The contextual action was activated in the local browser. It switched to the existing Chassis Lookup tab, pre-filled `AGH30-0015779`, retained the ALPHARD Sheet record and displayed its year, color, location, date and THB price. The same view rendered the Copy chassis button and all five source links, including the Alphard-specific Goo-net catalog link. This confirms that the new action is a navigation/handoff enhancement and does not modify the underlying Sheet vehicle record.
