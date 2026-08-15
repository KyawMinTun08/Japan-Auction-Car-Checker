# Combined Demo Verification

## Pull request state

PR #49 (`feature/hybrid-source-check-detail-20260815` → `main`) remains open. It contains the preceding source-link feature as well as the contextual car-detail handoff, so it is the single website PR intended for review. It has not been merged or deployed to GitHub Pages.

## Demo environments

The local JACC branch previously verified the car detail to Chassis Lookup handoff using `AGH30-0015779`. The separate published source-check preview domain returned an empty page at the time of this check; it cannot be used as a reliable user demo link until the hosting state is corrected. The bot UI remains a website-only preview; the live Railway bot has not been changed.

The local source-check preview at port 3000 loaded normally and accepted `AGH30-0015779`. It is suitable for the interactive bot UI demo, but it is a temporary preview environment rather than the deployed JACC website.

## Source-check and bot preview

After `Source Check` was selected for `AGH30-0015779`, the local preview rendered five source handoff cards, a Copy chassis action, and the Telegram visual preview. The preview showed the intended `/check AGH30-0015779` command, bot reply, Copy chassis button, and SBT Japan, Goo-net, and Real Motor inline source buttons. It is explicitly labelled preview-only and does not represent a live Telegram response.
