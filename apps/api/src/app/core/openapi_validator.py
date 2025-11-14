from __future__ import annotations
import json
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class OpenAPIValidator:
    """Validator for OpenAPI specification"""
    
    def __init__(self, spec_path: str):
        self.spec_path = Path(spec_path)
        self.spec = self._load_spec()
    
    def _load_spec(self) -> Dict[str, Any]:
        """Load OpenAPI specification"""
        try:
            with open(self.spec_path, 'r') as f:
                if self.spec_path.suffix == '.yaml' or self.spec_path.suffix == '.yml':
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to load OpenAPI spec: {e}")
    
    def validate_security_schemes(self) -> List[str]:
        """Validate security schemes are properly defined"""
        errors = []
        
        if 'components' not in self.spec:
            errors.append("Missing 'components' section")
            return errors
        
        if 'securitySchemes' not in self.spec['components']:
            errors.append("Missing 'securitySchemes' in components")
            return errors
        
        security_schemes = self.spec['components']['securitySchemes']
        
        # Check for required security schemes
        required_schemes = ['bearerAuth']
        for scheme in required_schemes:
            if scheme not in security_schemes:
                errors.append(f"Missing required security scheme: {scheme}")
        
        # Validate bearerAuth scheme
        if 'bearerAuth' in security_schemes:
            bearer_auth = security_schemes['bearerAuth']
            if bearer_auth.get('type') != 'http':
                errors.append("bearerAuth must be type 'http'")
            if bearer_auth.get('scheme') != 'bearer':
                errors.append("bearerAuth must use 'bearer' scheme")
            if bearer_auth.get('bearerFormat') != 'JWT':
                errors.append("bearerAuth must specify 'JWT' bearerFormat")
        
        return errors
    
    def validate_required_headers(self) -> List[str]:
        """Validate that required headers are defined as parameters"""
        errors = []
        
        required_headers = ['X-Tenant-Id', 'Idempotency-Key']
        
        if 'components' not in self.spec or 'parameters' not in self.spec['components']:
            errors.append("Missing 'parameters' in components")
            return errors
        
        parameters = self.spec['components']['parameters']
        
        for header in required_headers:
            if header not in parameters:
                errors.append(f"Missing required parameter: {header}")
            else:
                param = parameters[header]
                if param.get('in') != 'header':
                    errors.append(f"Parameter {header} must be 'in: header'")
                if param.get('name') != header:
                    errors.append(f"Parameter {header} name must match header name")
        
        return errors
    
    def validate_pagination_params(self) -> List[str]:
        """Validate pagination parameters"""
        errors = []
        
        if 'components' not in self.spec or 'parameters' not in self.spec['components']:
            errors.append("Missing 'parameters' in components")
            return errors
        
        parameters = self.spec['components']['parameters']
        
        # Check limit parameter
        if 'limit' not in parameters:
            errors.append("Missing 'limit' parameter")
        else:
            limit_param = parameters['limit']
            if limit_param.get('in') != 'query':
                errors.append("limit parameter must be 'in: query'")
            schema = limit_param.get('schema', {})
            if schema.get('minimum') != 1:
                errors.append("limit parameter minimum must be 1")
            if schema.get('maximum') != 200:
                errors.append("limit parameter maximum must be 200")
        
        # Check cursor parameter
        if 'cursor' not in parameters:
            errors.append("Missing 'cursor' parameter")
        else:
            cursor_param = parameters['cursor']
            if cursor_param.get('in') != 'query':
                errors.append("cursor parameter must be 'in: query'")
            schema = cursor_param.get('schema', {})
            if schema.get('type') != 'string':
                errors.append("cursor parameter must be type 'string'")
            if not schema.get('nullable'):
                errors.append("cursor parameter must be nullable")
        
        return errors
    
    def validate_endpoint_security(self) -> List[str]:
        """Validate that protected endpoints have security requirements"""
        errors = []
        
        if 'paths' not in self.spec:
            errors.append("Missing 'paths' section")
            return errors
        
        # Endpoints that should be protected
        protected_patterns = [
            '/users', '/tenants', '/chats', '/rag', '/analyze', '/jobs', '/artifacts'
        ]
        
        # Endpoints that should not be protected
        public_patterns = [
            '/healthz', '/readyz', '/version', '/auth/login', '/auth/refresh', 
            '/auth/.well-known/jwks.json', '/models'
        ]
        
        for path, methods in self.spec['paths'].items():
            for method, operation in methods.items():
                if method.upper() not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                    continue
                
                operation_id = operation.get('operationId', f"{method.upper()} {path}")
                
                # Check if endpoint should be protected
                should_be_protected = any(pattern in path for pattern in protected_patterns)
                should_be_public = any(pattern in path for pattern in public_patterns)
                
                if should_be_protected and not should_be_public:
                    if 'security' not in operation:
                        errors.append(f"Protected endpoint {operation_id} missing security requirement")
                    else:
                        security = operation['security']
                        if not security or len(security) == 0:
                            errors.append(f"Protected endpoint {operation_id} has empty security requirement")
                
                if should_be_public and 'security' in operation:
                    errors.append(f"Public endpoint {operation_id} should not have security requirement")
        
        return errors
    
    def validate_response_codes(self) -> List[str]:
        """Validate that endpoints have proper response codes"""
        errors = []
        
        if 'paths' not in self.spec:
            errors.append("Missing 'paths' section")
            return errors
        
        for path, methods in self.spec['paths'].items():
            for method, operation in methods.items():
                if method.upper() not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                    continue
                
                operation_id = operation.get('operationId', f"{method.upper()} {path}")
                
                if 'responses' not in operation:
                    errors.append(f"Endpoint {operation_id} missing responses")
                    continue
                
                responses = operation['responses']
                
                # Check for required response codes
                required_codes = ['200', '400', '401', '500']
                
                for code in required_codes:
                    if code not in responses:
                        if code == '200' and method.upper() in ['POST', 'PUT', 'PATCH']:
                            # POST/PUT/PATCH might return 201 instead of 200
                            if '201' not in responses:
                                errors.append(f"Endpoint {operation_id} missing {code} or 201 response")
                        elif code == '200' and method.upper() == 'DELETE':
                            # DELETE might return 204 instead of 200
                            if '204' not in responses:
                                errors.append(f"Endpoint {operation_id} missing {code} or 204 response")
                        else:
                            errors.append(f"Endpoint {operation_id} missing {code} response")
        
        return errors
    
    def validate_all(self) -> Dict[str, List[str]]:
        """Run all validations"""
        results = {
            'security_schemes': self.validate_security_schemes(),
            'required_headers': self.validate_required_headers(),
            'pagination_params': self.validate_pagination_params(),
            'endpoint_security': self.validate_endpoint_security(),
            'response_codes': self.validate_response_codes()
        }
        
        return results
    
    def is_valid(self) -> bool:
        """Check if specification is valid"""
        results = self.validate_all()
        return all(len(errors) == 0 for errors in results.values())
    
    def get_error_summary(self) -> str:
        """Get summary of all errors"""
        results = self.validate_all()
        
        total_errors = sum(len(errors) for errors in results.values())
        if total_errors == 0:
            return "OpenAPI specification is valid"
        
        summary = f"OpenAPI specification has {total_errors} errors:\n"
        
        for category, errors in results.items():
            if errors:
                summary += f"\n{category.replace('_', ' ').title()}:\n"
                for error in errors:
                    summary += f"  - {error}\n"
        
        return summary

def validate_openapi_spec(spec_path: str) -> bool:
    """Validate OpenAPI specification"""
    try:
        validator = OpenAPIValidator(spec_path)
        is_valid = validator.is_valid()
        
        if not is_valid:
            print(validator.get_error_summary())
        
        return is_valid
    except Exception as e:
        print(f"Validation failed: {e}")
        return False
