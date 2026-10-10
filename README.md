# Courtside background scheduler

This small repository calls the existing Courtside background updater every five minutes. It contains only the scheduler script, workflow and this guide. Courtside's application source, competition data, memberships and picks stay in Sites.

GitHub [provides free standard hosted runners for public repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions). This workflow uses the standard `ubuntu-latest` runner and creates no artifacts, caches, packages or paid runner resources. Keep this scheduler repository public and do not switch it to a private repository or a larger runner. No paid plan or spend increase is required for this template.

## Setup

1. Publish only the contents of this directory in a dedicated public repository, with `update.py` at its root and `.github/workflows/update.yml` on the default branch.
2. Store a separate random scheduler key as the repository Actions secret `COURTSIDE_UPDATER_KEY`. Configure its SHA-256 digest as `BACKGROUND_CRON_TOKEN_SHA256` in Courtside and set the app's background cadence to 300 seconds. Transfer the key through secret input, never source, command-line arguments or logs. This key authorizes only the protected background updater; it is separate from Sites service access.
3. Store Courtside's Sites service-access token separately as the encrypted repository Actions secret `COURTSIDE_SITE_SERVICE_TOKEN`. Sites requires this hosting-layer credential for POST requests before the app can check its dedicated updater key. The script sends `OAI-Sites-Authorization: Bearer ...` only to the exact Courtside HTTPS origin and updater path; neither credential is sent on the public status GET. Service access does not supply a signed-in visitor identity, and private competition membership and picks remain protected by the app's visitor checks.
4. Enable Actions for the repository and run **Update Courtside** manually once. Confirm the log reports `persisted:true`, then confirm Courtside's public Data status shows the same completed timestamp.

The Python script uses only the standard library. Both credentials enter the process through encrypted Actions secrets at runtime. It sends an empty JSON object to one exact HTTPS hostname, rejects redirects, bounds responses to 16 KiB and verifies the saved public status with an unauthenticated GET. A 120-second process deadline and three-minute workflow limit bound each run. It logs only controlled error codes and aggregate timestamps/status; it never logs either credential or raw responses. Repository token permissions are read-only, and checkout does not persist credentials.

## Timing and maintenance

The intended schedule is five minutes, offset from the top of the hour. GitHub's [scheduler can delay or drop queued runs](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), so this is not a real-time delivery guarantee. Courtside's durable lease and due-time guards coalesce overlapping or repeated calls. Browser updates continue separately while someone visits the app, and source outages remain visible as stale data.

GitHub automatically disables public scheduled workflows after **60 days without repository activity**. Review or re-enable the workflow when GitHub sends that notice; normal scheduled runs do not remove this maintenance requirement. Do not add artificial commits just to defeat the inactivity rule. The workflow must remain on the default branch. Manual dispatch uses the same protected handler.

The checkout action is pinned to the verified official [`actions/checkout` v7.0.1 commit](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1). Review the pin periodically with the scheduler.
