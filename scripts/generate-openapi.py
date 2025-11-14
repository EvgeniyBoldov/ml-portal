#!/usr/bin/env python3
"""
Generate OpenAPI schema from FastAPI application
"""
import sys
import json
import yaml
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api" / "src"))

try:
    from app.main import app
except ImportError as e:
    print(f"Error importing app: {e}")
    print("Make sure you're running from the project root and dependencies are installed")
    sys.exit(1)

def main():
    """Generate OpenAPI schema"""
    # Get OpenAPI schema from FastAPI app
    openapi_schema = app.openapi()
    
    # Output path
    output_path = Path(__file__).parent.parent / "api" / "openapi.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write as YAML
    with open(output_path, 'w') as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"✅ OpenAPI schema generated: {output_path}")
    print(f"   Total paths: {len(openapi_schema.get('paths', {}))}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

