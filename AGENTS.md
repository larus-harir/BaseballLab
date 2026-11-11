# BaseballLab development contract

Keep this repository and the working application; improve it incrementally.
The current user directive is `docs/specs/BaseballLab_Incremental_Redesign_Codex_Directive.md`.
User instructions take precedence over this file and archived plans.

## Stable responsibilities

- BaseballLab is the executable statistical player matchup program and owner of
  shared data, probability contracts and simulation services.
- Match owns competitive AI learning, adaptation and comparison with modern and
  historical human baseball. Its existing one-run experiment remains limited.
- EraMatch is the supplied KBO historical-player assignment's web application.
  Reproduction and improved candidates share the same engine, with different
  versions and evidence states. It is not AI-versus-human history research.
- The user's subsequent correction makes the supplied KBO season statistics
  application defaults. Ship only whitelisted matchup aggregates as package
  data; a fresh EraMatch must work offline without upload or manual connection.
  Do not ship the original ZIP/CSV/code/HWP or biographical CSV columns.

## Preservation and evidence

- Never delete, overwrite or regenerate existing originals, catalogs, research
  JSON, checkpoints, assignment files, logs or Git history as a redesign step.
  Read existing valid caches; write new runs/versions separately.
- Do not move storage directories just to match a new architecture.
- Never invent player profiles, seasons, missing event counts or research wins.
  Test fixtures must say MOCK_TEST_ONLY and never enter the production catalog.
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
- Delegate independent modules and reviews when useful. Give each agent explicit
  file ownership; coordinate contract changes before editing shared callers.

## Completion gates

- Record baseline and final tests, browser flows and original-file hashes.
- Exercise fresh data preparation, cached/offline/error paths, desktop/mobile,
  keyboard focus, saved report reopening and existing Match results.
- Preserve legacy reproduction and MLB 2024 regression metrics; validate new
  seasons with frozen settings and explain limitations and uncertainty.
- Before committing: run appropriate full tests, browser checks, `git diff --check`
  and `python scripts/audit_repository.py`; report failures and untested limits.
- Keep commits reviewable and provide SHA, run instructions and rollback guidance.
