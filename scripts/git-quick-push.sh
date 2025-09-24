#!/bin/bash

# Quick Git Push Script for ML Portal
# Usage: ./scripts/git-quick-push.sh "commit message"

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if commit message is provided
if [ $# -eq 0 ]; then
    echo -e "${RED}❌ Error: Please provide a commit message${NC}"
    echo -e "${YELLOW}Usage: ./scripts/git-quick-push.sh \"commit message\"${NC}"
    exit 1
fi

COMMIT_MESSAGE="$1"

echo -e "${BLUE}🚀 ML Portal - Quick Git Push${NC}"
echo -e "${BLUE}================================${NC}"

# Check git status
echo -e "${YELLOW}📋 Checking git status...${NC}"
git status --porcelain

# Add all changes
echo -e "${YELLOW}📦 Adding all changes...${NC}"
git add .

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo -e "${YELLOW}⚠️  No changes to commit${NC}"
    exit 0
fi

# Commit changes
echo -e "${YELLOW}💾 Committing changes...${NC}"
git commit -m "$COMMIT_MESSAGE"

# Push to origin
echo -e "${YELLOW}🚀 Pushing to origin...${NC}"
git push origin main

echo -e "${GREEN}✅ Successfully pushed to repository!${NC}"
echo -e "${BLUE}🔗 Repository: https://github.com/EvgeniyBoldov/ml-portal${NC}"
