#!/usr/bin/env python3
"""
OpenAPI validation script for CI/CD
"""
import sys
import os
from pathlib import Path

# Add the API app to Python path
api_path = Path(__file__).parent.parent / "apps" / "api" / "src"
sys.path.insert(0, str(api_path))

from app.core.openapi_validator import validate_openapi_spec

def main():
    """Main validation function"""
    # Path to OpenAPI spec
    spec_path = Path(__file__).parent.parent / "api" / "openapi.yaml"
    
    if not spec_path.exists():
        print(f"Error: OpenAPI spec not found at {spec_path}")
        return 1
    
    print(f"Validating OpenAPI spec: {spec_path}")
    
    # Validate the specification
    is_valid = validate_openapi_spec(str(spec_path))
    
    if is_valid:
        print("✅ OpenAPI specification is valid")
        return 0
    else:
        print("❌ OpenAPI specification validation failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
