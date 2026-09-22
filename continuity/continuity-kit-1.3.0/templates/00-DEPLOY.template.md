# 00-DEPLOY — {{project_name}} / {{deploy_name}}

> Deploy as a DOC, not as a loose command in someone's memory. Fill this in BEFORE running
> the real deploy — if you cannot fill in a section, the deploy is not ready.

## What changes

{{description_1_paragraph}}

## Steps (fixed order — do not skip)

1. **Backup/snapshot** of the current state: `{{backup_command}}`
2. **Build/staging** in a separate environment (never straight onto the live port): `{{build_staging_command}}`
3. **Canary** — exercise the critical path against staging: `{{canary_command}}`
4. **Promote** — stop the old one WITHOUT deleting it (rollback = switch it back on, not rebuild): `{{promote_command}}`
5. **Verify LIVE** — confirm that the BACKEND really switched (a route exclusive to the new one +
   build marker — not just the auth gate nor the process status): `{{verify_live_command}}`

## Rollback (see this change's `00-ROLLBACK.template.md`)

`{{link_to_00_rollback_of_this_change}}`

## Known gotcha of this project (if any)

{{project_specific_gotcha_or_none_yet}}

## Who authorises going to production

{{who_approves}} — always a human gate for a real deploy.
