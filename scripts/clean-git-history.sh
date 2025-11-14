#!/bin/bash
# Script to clean git history from .tar and sensitive .env files

set -e

echo "=== Cleaning Git History ==="
echo ""
echo "⚠️  WARNING: This will rewrite git history!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

# Remove .tar files from history
echo "1. Removing .tar, .tar.gz from history..."
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch *.tar *.tar.gz' \
  --prune-empty --tag-name-filter cat -- --all

# Remove sensitive env files from history (if any)
echo "2. Removing sensitive .env files from history..."
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env .env.dev .env.local env.dev' \
  --prune-empty --tag-name-filter cat -- --all

# Clean up
echo "3. Cleaning up..."
git for-each-ref --format="delete %(refname)" refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "✅ Git history cleaned!"
echo "⚠️  You'll need to force push: git push --force --all"
echo "⚠️  Make sure all team members are aware!"

