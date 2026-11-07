#!/bin/bash
# Friendly one-command test of devagent on a new PRIVATE GitHub repo.
# Run it with:   bash ~/Ai-Agent/try-devagent.sh

set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

AGENT_DIR="$HOME/Ai-Agent"
DEVAGENT="$AGENT_DIR/.venv/bin/devagent"
SAMPLE="$AGENT_DIR/examples/sample_repo"

say()  { printf "\n\033[1;36m👉 %s\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m✅ %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31m❌ %s\033[0m\n" "$1"; exit 1; }

echo
echo "=============================================="
echo "   devagent test - I'll guide you step by step"
echo "=============================================="

# --- checks ---------------------------------------------------------------
say "Checking your tools..."
[ -x "$DEVAGENT" ] || fail "devagent is not installed at $DEVAGENT"
command -v gh >/dev/null || fail "gh is not installed. Install it with: brew install gh"
gh auth status >/dev/null 2>&1 || fail "You are not logged in to GitHub. Run: gh auth login"
GH_USER=$(gh api user --jq .login)
ok "Everything is ready. GitHub account: $GH_USER"

# --- git name/email (needed to save changes) ------------------------------
if [ -z "$(git config --global user.name)" ] || [ -z "$(git config --global user.email)" ]; then
  say "Git needs your name and email to save changes (only needed once)."
  read -r -p "   Your name: " NAME
  read -r -p "   Your email: " EMAIL
  git config --global user.name "$NAME"
  git config --global user.email "$EMAIL"
  ok "Saved."
fi

# --- repo name -------------------------------------------------------------
say "What should the new PRIVATE GitHub repository be called?"
read -r -p "   Press Enter for 'devagent-test', or type a name: " REPO
REPO=${REPO:-devagent-test}
if gh repo view "$GH_USER/$REPO" >/dev/null 2>&1; then
  fail "You already have a repo called '$REPO'. Run this script again and pick another name."
fi
FOLDER="$HOME/$REPO"
[ -e "$FOLDER" ] && fail "A folder $FOLDER already exists. Run again and pick another name."

# --- create project + private repo ----------------------------------------
say "Creating the practice project in $FOLDER ..."
cp -R "$SAMPLE" "$FOLDER"
cd "$FOLDER"
git init -q -b main
git add -A
git commit -q -m "first version"
ok "Project created."

say "Creating the private repository on GitHub..."
gh repo create "$REPO" --private --source=. --push >/dev/null
ok "Private repo created: https://github.com/$GH_USER/$REPO"

# --- task ------------------------------------------------------------------
DEFAULT_TASK="Add a slugify(text) function to sample/text.py that turns 'Héllo World!' into 'hello-world'"
say "What should the AI build?"
echo "   Press Enter to use the example:"
echo "   \"$DEFAULT_TASK\""
read -r -p "   Or type your own idea: " TASK
TASK=${TASK:-$DEFAULT_TASK}

# --- run -------------------------------------------------------------------
say "Starting devagent! It will stop and ask you 2 questions:"
echo "   1) The PLAN   -> type  a  and press Enter to approve"
echo "   2) SEND IT?   -> type  y  and press Enter to open the pull request"
read -r -p "   Press Enter to start..." _

if "$DEVAGENT" run "$TASK" --repo "$FOLDER"; then
  ok "Finished!"
  say "Opening your pull request in the browser..."
  gh pr view --web 2>/dev/null || echo "   (No pull request was opened - maybe you answered 'n'.)"
else
  printf "\n\033[1;33m⚠️  devagent stopped before finishing. Copy the message above and ask Claude about it.\033[0m\n"
fi

echo
echo "When you're done, you can delete the practice repo on github.com:"
echo "   https://github.com/$GH_USER/$REPO/settings  ->  scroll down  ->  Delete this repository"
echo
