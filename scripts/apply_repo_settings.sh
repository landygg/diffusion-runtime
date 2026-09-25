#!/usr/bin/env bash
# Apply this repo's GitHub settings as code. Idempotent: safe to re-run.
#
#   scripts/apply_repo_settings.sh <owner>/<repo> [--lock-interactions]
#
# Needs `gh` logged in as the repo admin. Rulesets on a PRIVATE repo need
# GitHub Pro (personal accounts); secret scanning / fork-approval steps only
# apply to PUBLIC repos. Steps that don't apply are reported and skipped.
set -euo pipefail

REPO="${1:?usage: $0 <owner>/<repo> [--lock-interactions]}"
LOCK="${2:-}"
cd "$(dirname "$0")/.."

try() { local what="$1"; shift; if "$@" >/dev/null 2>&1; then echo "  ok    $what"; else echo "  skip  $what (not available for this repo/plan)"; fi; }

visibility=$(gh api "repos/$REPO" --jq .visibility)
echo "== $REPO ($visibility)"

echo "-- repository"
try "squash-only merges, auto-merge, delete merged branches, no wiki/projects" \
  gh api -X PATCH "repos/$REPO" \
    -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
    -F allow_auto_merge=true -F delete_branch_on_merge=true \
    -F has_wiki=false -F has_projects=false -F has_discussions=false
# Issues stay on: Renovate's Dependency Dashboard lives in an issue.
try "Dependabot vulnerability alerts" gh api -X PUT "repos/$REPO/vulnerability-alerts"

echo "-- actions"
try "default GITHUB_TOKEN = read-only, cannot approve PRs" \
  gh api -X PUT "repos/$REPO/actions/permissions/workflow" \
    -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
try "only GitHub-owned + docker/* actions allowed" \
  gh api -X PUT "repos/$REPO/actions/permissions" -F enabled=true -f allowed_actions=selected
try "allow-list: docker/*" \
  gh api -X PUT "repos/$REPO/actions/permissions/selected-actions" \
    -F github_owned_allowed=true -F verified_allowed=false -f 'patterns_allowed[]=docker/*'

if [[ "$visibility" == "public" ]]; then
  echo "-- public-repo protections"
  try "fork PRs from any external contributor need approval to run workflows" \
    gh api -X PUT "repos/$REPO/actions/permissions/fork-pr-contributor-approval" \
      -f approval_policy=all_external_contributors
  try "private vulnerability reporting (SECURITY.md points here)" \
    gh api -X PUT "repos/$REPO/private-vulnerability-reporting"
  try "secret scanning + push protection" \
    gh api -X PATCH "repos/$REPO" --input - <<JSON
{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}}
JSON
  if [[ "$LOCK" == "--lock-interactions" ]]; then
    # GitHub caps this at 6 months: re-run the script to renew.
    try "issues/PRs/comments limited to collaborators (6 months)" \
      gh api -X PUT "repos/$REPO/interaction-limits" -f limit=collaborators_only -f expiry=six_months
  fi
fi

echo "-- rulesets"
apply_ruleset() {  # $1 = name, $2 = json file; prints ok/skip
  local id
  id=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$1\") | .id" 2>/dev/null || true)
  if [[ -n "$id" ]]; then
    gh api -X PUT "repos/$REPO/rulesets/$id" --input "$2" >/dev/null 2>&1
  else
    gh api -X POST "repos/$REPO/rulesets" --input "$2" >/dev/null 2>&1
  fi
}
for f in .github/rulesets/*.json; do
  name=$(jq -r .name "$f")
  if apply_ruleset "$name" "$f"; then
    echo "  ok    ruleset '$name'"
  else
    # An app (Renovate) can only be a bypass actor once it is installed on the repo.
    tmp=$(mktemp)
    jq '.bypass_actors |= map(select(.actor_type != "Integration"))' "$f" > "$tmp"
    if apply_ruleset "$name" "$tmp"; then
      echo "  ok    ruleset '$name' WITHOUT app bypass (install the app, then re-run)"
    else
      echo "  FAIL  ruleset '$name'"; gh api -X POST "repos/$REPO/rulesets" --input "$tmp" 2>&1 | tail -1
    fi
    rm -f "$tmp"
  fi
done
