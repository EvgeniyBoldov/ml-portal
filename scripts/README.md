# Scripts Directory

This directory contains utility scripts for the ML Portal project.

## Available Scripts

### 🚀 Git Quick Push (`git-quick-push.sh`)

A convenient script for quickly adding, committing, and pushing changes to the repository.

**Usage:**
```bash
# Direct usage
./scripts/git-quick-push.sh "your commit message"

# Via Makefile
make git-push MSG="your commit message"
```

**Features:**
- ✅ Adds all changes automatically
- ✅ Commits with your message
- ✅ Pushes to origin/main
- ✅ Colorized output
- ✅ Error handling
- ✅ Status checking

**Example:**
```bash
make git-push MSG="fix: resolve authentication issue in login flow"
```

### 📄 Code Generation (`generate_code.py`)

Generates a comprehensive single-file documentation of the entire project codebase.

**Usage:**
```bash
# Direct usage
python3 scripts/generate_code.py

# Via Makefile
make gen-code
```

**Output:** `docs/generated/full_code.txt`

**Features:**
- ✅ Categorizes code by type (Infra, Backend, Frontend, Tests, etc.)
- ✅ Includes file metadata (size, type, lines)
- ✅ Provides project statistics
- ✅ Excludes generated files and cache directories
- ✅ Auto-deletes old generated files

## Repository Cleanup

The repository has been cleaned up to remove:

### ❌ Removed Files:
- **IDE artifacts**: `.idea/`, `.vscode/`
- **OS files**: `.DS_Store`, `Thumbs.db`
- **Python cache**: `__pycache__/`, `*.pyc`, `*.pyo`
- **Build artifacts**: `dist/`, `build/`, `coverage/`
- **Temporary files**: `*.log`, `*.tmp`, `*~`
- **Environment files**: `.env` (removed from tracking)

### ✅ Updated `.gitignore`:
- Local environment files (`.env*`)
- Python virtual environments (`venv/`, `env/`)
- Testing artifacts (`.pytest_cache/`, `.coverage`)
- Build artifacts (`dist/`, `build/`, `*.egg-info`)
- IDE files (`.vscode/`, `.idea/`)
- OS files (`.DS_Store`, `Thumbs.db`)
- Node.js artifacts (`node_modules/`, `*.log`)
- TypeScript build info (`*.tsbuildinfo`)
- Temporary files (`*.tmp`, `*.temp`, `*~`)

## Security Check

The repository has been scanned for potential secrets:

```bash
git grep -n "SECRET\|API_KEY\|PASSWORD\|TOKEN"
```

✅ **No real secrets found** - only configuration variables and test passwords.

## Quick Commands Reference

```bash
# Development
make dev              # Start development environment
make prod             # Start production environment
make down             # Stop all services

# Testing
make test             # Run all tests
make test-backend     # Run backend tests only
make test-frontend    # Run frontend tests only

# Git Operations
make git-push MSG="message"  # Quick git add, commit, push

# Code Generation
make gen-code         # Generate full project code documentation

# Maintenance
make clean            # Clean up containers and volumes
make clean-all        # Clean up everything including images
```

## Repository Status

- **Repository**: https://github.com/EvgeniyBoldov/ml-portal
- **Branch**: `main`
- **Status**: ✅ Clean and secure
- **Last cleanup**: Repository sanitized and optimized
