#!/usr/bin/env bash
#
# Applies the repository settings a GitHub template cannot carry: the branch ruleset,
# the merge policy and the secret-scanning switches. A template copies files, not
# configuration, so without this every new project starts with an unprotected main.
#
# Idempotent: re-running it reports the ruleset already exists and changes nothing else.
#
# Usage:  scripts/setup-github.sh [owner/repo]
#         Defaults to the repository the current directory points at.

set -euo pipefail

REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
RULESET_FILE="$(dirname "$0")/ruleset-main.json"
RULESET_NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$RULESET_FILE")"

echo "==> Configuring $REPO"

# --- Merge policy ---------------------------------------------------------------------
# Squash only, and delete the branch afterwards. Matches the trunk-based workflow in
# CLAUDE.md: linear history, one commit per pull request.
echo "--> Merge policy: squash only, delete branch on merge"
gh repo edit "$REPO" \
  --enable-squash-merge \
  --enable-merge-commit=false \
  --enable-rebase-merge=false \
  --delete-branch-on-merge >/dev/null

# --- Branch ruleset -------------------------------------------------------------------
# Targets ~DEFAULT_BRANCH rather than a branch name, so it survives a rename.
if gh api "repos/$REPO/rulesets" --jq '.[].name' 2>/dev/null | grep -qx "$RULESET_NAME"; then
  echo "--> Ruleset '$RULESET_NAME' already exists, leaving it alone"
else
  echo "--> Creating ruleset '$RULESET_NAME' (required checks, PR required, no force push)"
  gh api "repos/$REPO/rulesets" --method POST --input "$RULESET_FILE" >/dev/null
fi

# --- Secret scanning ------------------------------------------------------------------
# Free on public repositories. gitleaks in CI scans the history; push protection stops a
# secret before it is ever pushed. Complementary, so both are enabled.
echo "--> Secret scanning and push protection"
if gh api "repos/$REPO" --method PATCH \
  --raw-field 'security_and_analysis[secret_scanning][status]=enabled' \
  --raw-field 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
  >/dev/null 2>&1; then
  echo "    enabled"
else
  echo "    could not enable them from the API — turn them on in"
  echo "    Settings > Advanced Security. On a private repository they need a paid plan."
fi

# --- What is left --------------------------------------------------------------------
cat <<'EOF'

==> Done. Still manual:

  * Mark the repository as a template, if this is a template:
      gh repo edit --template

  * If this repository is PRIVATE, CodeQL will fail: code scanning is free only on
    public repositories. Either pay for GitHub Code Security, or delete
    .github/workflows/codeql.yml and remove "CodeQL" and "analyze (python)" from
    scripts/ruleset-main.json before running this script.

  * Repository secrets, which are per project and must never be committed:
      gh secret set DATABASE_URL_PRODUCTION

Verify with:
  gh api repos/OWNER/REPO/rulesets --jq '.[].name'
  gh repo view OWNER/REPO --json isTemplate,deleteBranchOnMerge,squashMergeAllowed
EOF
