# 00-DEPLOY — {{project_name}} / {{deploy_nome}}

> Deploy as a DOC, not as a loose command in someone's memory. Fill this in BEFORE running
> the real deploy — if you cannot fill in a section, the deploy is not ready.

## What changes

{{descricao_1_paragrafo}}

## Steps (fixed order — do not skip)

1. **Backup/snapshot** of the current state: `{{comando_backup}}`
2. **Build/staging** in a separate environment (never straight onto the live port): `{{comando_build_staging}}`
3. **Canary** — exercise the critical path against staging: `{{comando_canary}}`
4. **Promote** — stop the old one WITHOUT deleting it (rollback = switch it back on, not rebuild): `{{comando_promote}}`
5. **Verify LIVE** — confirm that the BACKEND really switched (a route exclusive to the new one +
   build marker — not just the auth gate nor the process status): `{{comando_verify_live}}`

## Rollback (see this change's `00-ROLLBACK.template.md`)

`{{link_para_00_rollback_desta_mudanca}}`

## Known gotcha of this project (if any)

{{gotcha_especifico_ou_nenhum_ainda}}

## Who authorises going to production

{{quem_aprova}} — always a human gate for a real deploy.
