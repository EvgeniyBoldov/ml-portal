#!/usr/bin/env python3
"""
Check that no files import 'settings' directly from app.core.config
This script should be run in CI to ensure we only use get_settings()
"""
import os
import sys
import subprocess
from pathlib import Path

def check_settings_imports():
    """Check for direct settings imports"""
    # Find the app directory
    app_dir = Path(__file__).parent.parent / "apps" / "api" / "src" / "app"
    
    if not app_dir.exists():
        print(f"Error: App directory not found at {app_dir}")
        return 1
    
    # Search for direct settings imports
    try:
        result = subprocess.run([
            "grep", "-r", "-n", 
            "from app.core.config import settings",
            str(app_dir)
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("❌ Found direct settings imports:")
            print(result.stdout)
            return 1
        else:
            print("✅ No direct settings imports found")
            return 0
            
    except FileNotFoundError:
        print("Error: grep command not found")
        return 1

if __name__ == "__main__":
    sys.exit(check_settings_imports())
