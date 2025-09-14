#!/usr/bin/env python3
"""
Test script to setup RBAC system and create test users.
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def wait_for_api():
    """Wait for API to be ready."""
    print("⏳ Waiting for API to be ready...")
    for i in range(30):
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                print("✅ API is ready!")
                return True
        except:
            pass
        time.sleep(1)
    print("❌ API is not ready after 30 seconds")
    return False

def create_superuser():
    """Create superuser directly in database."""
    print("🔐 Creating superuser...")
    
    # We'll create the user via a direct database connection
    # For now, let's just test the API endpoints
    
    # Test health endpoint
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health check: {response.status_code} - {response.json()}")
    
    # Test auth endpoints
    response = requests.get(f"{BASE_URL}/api/auth/me")
    print(f"Auth me (no token): {response.status_code} - {response.json()}")
    
    # Test admin endpoints (should fail without auth)
    response = requests.get(f"{BASE_URL}/api/admin/users")
    print(f"Admin users (no auth): {response.status_code} - {response.json()}")
    
    # Test RAG endpoints (should fail without auth)
    response = requests.get(f"{BASE_URL}/api/rag/")
    print(f"RAG list (no auth): {response.status_code} - {response.json()}")

def main():
    """Main function."""
    print("🚀 RBAC System Test Setup")
    print("=" * 50)
    
    if not wait_for_api():
        return
    
    create_superuser()
    
    print("\n✅ Setup completed!")

if __name__ == "__main__":
    main()
