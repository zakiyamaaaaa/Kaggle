#!/bin/bash
set -euo pipefail
ROOT="/Users/shoichiyamazaki/Kaggle"
LOG="$ROOT/.setup_github.log"
exec > >(tee "$LOG") 2>&1

echo "=== setup github $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
cd "$ROOT"

# Use single repo at Kaggle root (remove nested git if present)
if [ -d "$ROOT/ai_agent_security/.git" ]; then
  echo "Removing nested git in ai_agent_security/.git"
  rm -rf "$ROOT/ai_agent_security/.git"
fi

if [ ! -d "$ROOT/.git" ]; then
  git init
fi

git add -A
git status

if git diff --cached --quiet; then
  echo "Nothing to commit"
else
  git commit -m "$(cat <<'EOF'
Initial commit: Kaggle workspace with ai_agent_security project.

EOF
)"
fi

# Create GitHub repo if no remote
if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create Kaggle --private --source=. --remote=origin --push --description "Kaggle competition workspace"
else
  echo "Remote origin already set: $(git remote get-url origin)"
  git push -u origin HEAD
fi

echo "=== done ==="
git remote -v
git log -1 --oneline
