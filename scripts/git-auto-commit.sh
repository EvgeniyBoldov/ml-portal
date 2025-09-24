#!/bin/bash

# Auto Git Commit Script for ML Portal
# Automatically generates commit message based on file changes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 ML Portal - Auto Git Commit${NC}"
echo -e "${BLUE}===============================${NC}"

# Check if there are any changes
if git diff --quiet && git diff --cached --quiet; then
    echo -e "${YELLOW}⚠️  No changes to commit${NC}"
    exit 0
fi

# Get current date
CURRENT_DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Analyze changes
echo -e "${YELLOW}📋 Analyzing changes...${NC}"

# Get modified files
MODIFIED_FILES=$(git diff --name-only --cached 2>/dev/null || git diff --name-only 2>/dev/null || echo "")
UNTRACKED_FILES=$(git ls-files --others --exclude-standard 2>/dev/null || echo "")

# Count changes
MODIFIED_COUNT=$(echo "$MODIFIED_FILES" | grep -v '^$' | wc -l)
UNTRACKED_COUNT=$(echo "$UNTRACKED_FILES" | grep -v '^$' | wc -l)
TOTAL_COUNT=$((MODIFIED_COUNT + UNTRACKED_COUNT))

if [ $TOTAL_COUNT -eq 0 ]; then
    echo -e "${YELLOW}⚠️  No changes to commit${NC}"
    exit 0
fi

# Categorize files
BACKEND_FILES=$(echo -e "$MODIFIED_FILES\n$UNTRACKED_FILES" | grep -E '^apps/api/' | grep -v '^$' | wc -l)
FRONTEND_FILES=$(echo -e "$MODIFIED_FILES\n$UNTRACKED_FILES" | grep -E '^apps/web/' | grep -v '^$' | wc -l)
INFRA_FILES=$(echo -e "$MODIFIED_FILES\n$UNTRACKED_FILES" | grep -E '^(infra/|docker-compose|Makefile|\.gitignore)' | grep -v '^$' | wc -l)
DOCS_FILES=$(echo -e "$MODIFIED_FILES\n$UNTRACKED_FILES" | grep -E '^docs/' | grep -v '^$' | wc -l)
SCRIPTS_FILES=$(echo -e "$MODIFIED_FILES\n$UNTRACKED_FILES" | grep -E '^scripts/' | grep -v '^$' | wc -l)
TESTS_FILES=$(echo -e "$MODIFIED_FILES\n$UNTRACKED_FILES" | grep -E 'test' | grep -v '^$' | wc -l)

# Determine commit type and scope
COMMIT_TYPE="update"
COMMIT_SCOPE=""

if [ $TESTS_FILES -gt 0 ]; then
    COMMIT_TYPE="test"
    COMMIT_SCOPE="tests"
elif [ $BACKEND_FILES -gt 0 ] && [ $FRONTEND_FILES -gt 0 ]; then
    COMMIT_TYPE="feat"
    COMMIT_SCOPE="fullstack"
elif [ $BACKEND_FILES -gt 0 ]; then
    COMMIT_TYPE="feat"
    COMMIT_SCOPE="backend"
elif [ $FRONTEND_FILES -gt 0 ]; then
    COMMIT_TYPE="feat"
    COMMIT_SCOPE="frontend"
elif [ $INFRA_FILES -gt 0 ]; then
    COMMIT_TYPE="chore"
    COMMIT_SCOPE="infra"
elif [ $DOCS_FILES -gt 0 ]; then
    COMMIT_TYPE="docs"
    COMMIT_SCOPE="documentation"
elif [ $SCRIPTS_FILES -gt 0 ]; then
    COMMIT_TYPE="chore"
    COMMIT_SCOPE="scripts"
fi

# Generate commit message
COMMIT_MESSAGE="${COMMIT_TYPE}(${COMMIT_SCOPE}): update ${TOTAL_COUNT} files"

# Add details about changes
DETAILS=""
if [ $MODIFIED_COUNT -gt 0 ]; then
    DETAILS="${DETAILS}${MODIFIED_COUNT} modified"
fi
if [ $UNTRACKED_COUNT -gt 0 ]; then
    if [ -n "$DETAILS" ]; then
        DETAILS="${DETAILS}, ${UNTRACKED_COUNT} added"
    else
        DETAILS="${UNTRACKED_COUNT} added"
    fi
fi

COMMIT_MESSAGE="${COMMIT_MESSAGE} (${DETAILS}) - ${CURRENT_DATE}"

# Show summary
echo -e "${CYAN}📊 Change Summary:${NC}"
echo -e "   📝 Modified: ${MODIFIED_COUNT} files"
echo -e "   ➕ Added: ${UNTRACKED_COUNT} files"
echo -e "   📁 Total: ${TOTAL_COUNT} files"
echo ""

if [ $BACKEND_FILES -gt 0 ]; then
    echo -e "   🔧 Backend: ${BACKEND_FILES} files"
fi
if [ $FRONTEND_FILES -gt 0 ]; then
    echo -e "   🎨 Frontend: ${FRONTEND_FILES} files"
fi
if [ $INFRA_FILES -gt 0 ]; then
    echo -e "   🏗️  Infrastructure: ${INFRA_FILES} files"
fi
if [ $DOCS_FILES -gt 0 ]; then
    echo -e "   📚 Documentation: ${DOCS_FILES} files"
fi
if [ $SCRIPTS_FILES -gt 0 ]; then
    echo -e "   🛠️  Scripts: ${SCRIPTS_FILES} files"
fi
if [ $TESTS_FILES -gt 0 ]; then
    echo -e "   🧪 Tests: ${TESTS_FILES} files"
fi

echo ""
echo -e "${CYAN}💬 Commit Message:${NC}"
echo -e "   ${COMMIT_MESSAGE}"
echo ""

# Add all changes
echo -e "${YELLOW}📦 Adding all changes...${NC}"
git add .

# Commit changes
echo -e "${YELLOW}💾 Committing changes...${NC}"
git commit -m "$COMMIT_MESSAGE"

# Push to origin
echo -e "${YELLOW}🚀 Pushing to origin...${NC}"
git push origin main

echo ""
echo -e "${GREEN}✅ Successfully committed and pushed!${NC}"
echo -e "${BLUE}🔗 Repository: https://github.com/EvgeniyBoldov/ml-portal${NC}"
echo -e "${CYAN}📝 Commit: ${COMMIT_MESSAGE}${NC}"
