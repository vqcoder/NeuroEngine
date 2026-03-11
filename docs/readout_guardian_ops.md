# Readout Guardian Ops

## 1) Required CI Check (GitHub)

Target required status check name:

- `readout-guardian`

Workflow file:

- `.github/workflows/readout-guardian-check.yml`

Attempt to enforce on `main`:

```bash
gh api \
  --method PUT \
  repos/johnvqcapital/neurotrace/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks.strict=true \
  -f required_status_checks.contexts[]="readout-guardian" \
  -f enforce_admins=true \
  -F required_pull_request_reviews='{}' \
  -F restrictions='null'
```

If GitHub returns `403 Upgrade to GitHub Pro...`, this repo plan cannot enforce required checks on private repos.

Fallback while on current plan:

- keep `readout-guardian-check.yml` running on every PR/push
- merge only after `readout-guardian` is green
- do not merge baseline changes unless a new approved run metadata file exists under `ml/training/approved_runs/`

## 2) Baseline Refresh (Approved Learning Runs Only)

Create approved metadata file:

- `ml/training/approved_runs/<run_id>.json`

Then dispatch workflow:

```bash
gh workflow run "Readout Guardian Baseline Update" \
  -f metadata_path="ml/training/approved_runs/<run_id>.json"
```

What the workflow enforces:

- metadata path must be under `ml/training/approved_runs/*.json`
- metadata must pass validator in `services/biograph_api/app/readout_learning_metadata.py`
- baseline is regenerated and a PR is opened with only:
  - `services/biograph_api/app/readout_guardian_baseline.json`
