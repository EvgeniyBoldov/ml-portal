#!/usr/bin/env python3
"""
Generate smoke tests from OpenAPI specification
"""
import sys
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List

def load_openapi_spec(spec_path: Path) -> Dict[str, Any]:
    """Load OpenAPI specification"""
    with open(spec_path, 'r') as f:
        return yaml.safe_load(f)

def generate_smoke_test(path: str, method: str, operation: Dict[str, Any]) -> str:
    """Generate smoke test for an endpoint"""
    operation_id = operation.get('operationId', f"{method.upper()}_{path.replace('/', '_').replace('{', '').replace('}', '')}")
    
    # Skip auth endpoints for smoke tests
    if '/auth/' in path:
        return ""
    
    # Generate test
    test_code = f"""
@pytest.mark.smoke
async def test_{operation_id.lower()}(client: AsyncClient):
    \"\"\"Smoke test for {method.upper()} {path}\"\"\"
    # This is a generated smoke test - implement actual test logic
    response = await client.{method.lower()}("{path}")
    
    # Basic assertions
    assert response.status_code in [200, 201, 204, 400, 401, 403, 404, 422]
    
    # Add more specific assertions based on expected response codes
    if response.status_code in [200, 201]:
        assert response.headers.get("content-type", "").startswith("application/json")
"""
    
    return test_code

def generate_smoke_tests(spec: Dict[str, Any]) -> str:
    """Generate all smoke tests"""
    tests = []
    
    # Add imports
    tests.append("""
import pytest
from httpx import AsyncClient

# Generated smoke tests from OpenAPI specification
""")
    
    # Generate tests for each endpoint
    for path, methods in spec.get('paths', {}).items():
        for method, operation in methods.items():
            if method.upper() in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                test = generate_smoke_test(path, method, operation)
                if test.strip():
                    tests.append(test)
    
    return "\n".join(tests)

def main():
    """Main function"""
    # Path to OpenAPI spec
    spec_path = Path(__file__).parent.parent / "api" / "openapi.yaml"
    
    if not spec_path.exists():
        print(f"Error: OpenAPI spec not found at {spec_path}")
        return 1
    
    # Load specification
    spec = load_openapi_spec(spec_path)
    
    # Generate tests
    tests = generate_smoke_tests(spec)
    
    # Write to file
    output_path = Path(__file__).parent.parent / "apps" / "api" / "src" / "app" / "tests" / "smoke" / "test_generated_smoke.py"
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write(tests)
    
    print(f"Generated smoke tests: {output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
