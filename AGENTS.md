# BaseballLab development contract

Keep this repository and the working application; improve it incrementally.
The current product directive is `docs/specs/BaseballLab_Design_First_Codex_Directive.md`.
User instructions take precedence over this file and archived plans.

## Stable responsibilities

- BaseballLab is the executable statistical player matchup program and owner of
  shared data, probability contracts and simulation services.
- Match owns competitive self-play for studying learned baseball choices, not ranking teams. The default pitch-game v5 trains **one shared offense policy and one shared pitching policy** from both trajectory roles, with terminal game wins/losses only. Use the hash-checked observed-tracking asset for complete family/course/speed observations in MLB2017–2021/2024–2026, KBO2026 Lotte-participant games and NPB2019–2026. Keep chronological holdouts, fit-only speed bands, source-display coordinate frames and within-league/year native movement backoff. Give selected leagues equal practice opportunity and cycle their years; do not average other leagues into MLB. Results show unified executed choices, course heatmaps and identical-state preference changes, never A/B rankings or claims of global optimality. Pattern selection is an observational approximation with idealized perception, not measured intended targets or causal effects. Directional targets preserve ordinary-swing non-contact probabilities; unknown batting stance uses field directions. Do not fabricate missing positions or relabel source pixels as physical distance. Preserve the old 44-cohort corpus, original sources, all saved v1–v4 reports/checkpoints and all legacy study execution paths. Failed jobs show retry, not diagnostic results.
- EraMatch is the unified MLB/KBO player matchup experience; retain legacy
  project=baseball identifiers and /baseball compatibility. The supplied KBO assignment remains a distinct calculation mode.
  Reproduction and improved candidates share the same engine, with different
  versions and evidence states. It is not AI-versus-human history research.
- The user's subsequent correction makes the supplied KBO season statistics
  application defaults. Ship only whitelisted derived matchup/training counts as package
  data; a fresh EraMatch must work offline without upload or manual connection.
  Do not ship the original ZIP/CSV/code/HWP or biographical CSV columns.

## Preservation and evidence

- Never delete, overwrite or regenerate existing originals, catalogs, research
  JSON, checkpoints, assignment files, logs or Git history as a redesign step.
  Read existing valid caches; write new runs/versions separately.
- Do not move storage directories just to match a new architecture.
- Never invent player profiles, seasons, missing event counts or research wins.
  Test fixtures must say MOCK_TEST_ONLY and never enter the production catalog.
- Keep slow source/model I/O outside the shared state lock; reserve conflicting
  writes explicitly. Reject unsupported training dates before acquisition/jobs.
- Keep actual observations, fitted probabilities, virtual events, assumptions
  and validation conclusions distinct. Independent PA simulation is not 9 innings.
- A predictive test is not proof of causal strategy effects, scientific validity
  across leagues, security certification or usability certification.
- Retain fixed providers, source hashes, safe ZIP/path handling, Host/Origin/token
  protections, loopback binding and explicit two-step storage deletion.
- Do not commit private raw data, original assignment ZIP/PDF/code, credentials,
  local paths or learned weights. Do not claim Windows ACL/encryption is tested.

## Product and collaboration

- Normal use is project → league/season/player → run → explanation. Hide seed,
  model selection and data inspection settings under optional advanced details.
- Reuse `matchup`, the existing providers, catalog paths, Match training and
  reports. Do not create a second app or duplicate probability implementations.
- Main implements and reviews work alone. The user ended collection delegation;
  do not resume or spawn designer, QA or data agents unless the user requests
  delegation again. Keep design unchanged unless the user requests design
  changes. Avoid repeated repository-wide analysis.
- Read related files and the current directive rather than repeating whole-repo
  research or old plans. Reuse working code. Do not add unsolicited features,
  plans, documents, screenshots or repeated searches.
- Report only changed functionality, main files, test results and remaining
  problems, concisely. Run focused checks during work and full regression for
  core/data/security changes or final integration.

## Completion gates

- Record baseline and final tests, browser flows and original-file hashes.
- Exercise fresh data preparation, cached/offline/error paths, desktop/mobile,
  keyboard focus, saved report reopening and existing Match results.
- Preserve legacy reproduction and MLB 2024 regression metrics; validate new
  seasons with frozen settings and explain limitations and uncertainty.
- Before committing: run appropriate full tests, browser checks, `git diff --check`
  and `python scripts/audit_repository.py`; report failures and untested limits.
- Keep commits reviewable and provide SHA, run instructions and rollback guidance.
