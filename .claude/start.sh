#!/bin/bash
# Runs at the start of every Claude Code session, and again after /clear or a compaction (the SessionStart hook in
# .claude/settings.json). It sets the executive's time zone. In a cloud session it installs what the tools need and puts
# the vault on an up-to-date main, since each cloud session starts on a branch of its own. Then it prints the vault's
# status, which Claude reads first.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" || exit 0

# timeout(1) is not on macOS: there git runs without a time limit.
limit() { if command -v timeout >/dev/null 2>&1; then timeout "$@"; else shift; "$@"; fi; }

on_main() {
  git rev-parse --git-dir >/dev/null 2>&1 || return 0
  export GIT_TERMINAL_PROMPT=0
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
    limit 120 git fetch -q --unshallow origin >/dev/null 2>&1  # the review dates projects by their last commit
  fi
  if ! limit 60 git fetch -q origin main >/dev/null 2>&1; then
    echo "Git: main could not be fetched from GitHub, so this session may not see the latest vault."
    return 0
  fi
  local branch
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ "$branch" != "main" ]; then
    if [ -n "$(git status --porcelain --untracked-files=no)" ] || ! git merge-base --is-ancestor HEAD origin/main; then
      echo "Git: this session is on the branch $branch, which holds work not yet on main. Merge it into main and push" \
           "main, as CLAUDE.md says under Git."
      return 0
    fi
    if git show-ref -q --verify refs/heads/main; then
      git checkout -q main 2>/dev/null
    else
      git checkout -q -b main --track origin/main 2>/dev/null
    fi || { echo "Git: could not switch to main, so the session stays on $branch."; return 0; }
  fi
  git merge -q --ff-only origin/main >/dev/null 2>&1 \
    || echo "Git: main could not be brought up to date, as it has changes of its own. Commit them, then run" \
            "git pull --rebase origin main."
}

# The executive's time zone, from settings.json, for the dates of notes and commits in this session.
zone=$(python3 -c 'import json, zoneinfo; z = json.load(open("settings.json")).get("timezone") or ""; zoneinfo.ZoneInfo(z)
print(z)' 2>/dev/null)
if [ -n "$zone" ]; then
  export TZ="$zone"
  [ -n "$CLAUDE_ENV_FILE" ] && echo "export TZ=$zone" >> "$CLAUDE_ENV_FILE"
fi

if [ "$CLAUDE_CODE_REMOTE" = "true" ]; then
  python3 -m pip install -q -r requirements.txt >/dev/null 2>&1 \
    || python3 -m pip install -q --break-system-packages -r requirements.txt >/dev/null 2>&1
  on_main
fi
if ! status=$(python3 tools/vault.py status 2>&1); then
  echo "Vault status: not available ($(printf '%s\n' "$status" | tail -n 1))." \
       "Run python3 tools/vault.py status to see why."
  exit 0
fi
printf '%s\n' "$status"
exit 0
