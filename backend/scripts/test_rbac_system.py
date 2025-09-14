#!/usr/bin/env python3
"""
Test script for RBAC system.
This script demonstrates the admin functionality and RBAC system.
"""
import sys
import os
import requests
import json
from typing import Dict, Any

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.db import get_session
from app.core.security import hash_password
from app.repositories.users_repo import UsersRepo


class RBACTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.tokens = {}
    
    def login(self, username: str, password: str) -> bool:
        """Login and store token."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"login": username, "password": password}
            )
            if response.status_code == 200:
                data = response.json()
                self.tokens[username] = data["access_token"]
                print(f"✅ Logged in as {username}")
                return True
            else:
                print(f"❌ Login failed for {username}: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login error for {username}: {e}")
            return False
    
    def make_request(self, method: str, endpoint: str, username: str, **kwargs) -> requests.Response:
        """Make authenticated request."""
        if username not in self.tokens:
            raise ValueError(f"No token for user {username}")
        
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f"Bearer {self.tokens[username]}"
        kwargs['headers'] = headers
        
        return self.session.request(method, f"{self.base_url}{endpoint}", **kwargs)
    
    def test_rbac(self):
        """Test RBAC functionality."""
        print("\n🔐 Testing RBAC System")
        print("=" * 50)
        
        # Test admin access
        print("\n1. Testing admin access...")
        response = self.make_request("GET", "/api/admin/users", "admin")
        if response.status_code == 200:
            print("✅ Admin can access admin API")
        else:
            print(f"❌ Admin cannot access admin API: {response.status_code}")
        
        # Test editor access
        print("\n2. Testing editor access...")
        response = self.make_request("GET", "/api/rag/", "editor")
        if response.status_code == 200:
            print("✅ Editor can access RAG API")
        else:
            print(f"❌ Editor cannot access RAG API: {response.status_code}")
        
        response = self.make_request("GET", "/api/admin/users", "editor")
        if response.status_code == 403:
            print("✅ Editor correctly denied admin access")
        else:
            print(f"❌ Editor should be denied admin access: {response.status_code}")
        
        # Test reader access
        print("\n3. Testing reader access...")
        response = self.make_request("GET", "/api/rag/", "reader")
        if response.status_code == 200:
            print("✅ Reader can access RAG read operations")
        else:
            print(f"❌ Reader cannot access RAG read operations: {response.status_code}")
        
        response = self.make_request("GET", "/api/admin/users", "reader")
        if response.status_code == 403:
            print("✅ Reader correctly denied admin access")
        else:
            print(f"❌ Reader should be denied admin access: {response.status_code}")
    
    def test_admin_api(self):
        """Test admin API functionality."""
        print("\n👑 Testing Admin API")
        print("=" * 50)
        
        # Create a test user
        print("\n1. Creating test user...")
        user_data = {
            "login": "testuser",
            "password": "testuser123456",
            "role": "reader",
            "email": "testuser@example.com"
        }
        
        response = self.make_request("POST", "/api/admin/users", "admin", json=user_data)
        if response.status_code == 201:
            print("✅ Test user created successfully")
            user_id = response.json()["id"]
        else:
            print(f"❌ Failed to create test user: {response.text}")
            return
        
        # List users
        print("\n2. Listing users...")
        response = self.make_request("GET", "/api/admin/users", "admin")
        if response.status_code == 200:
            users = response.json()["users"]
            print(f"✅ Found {len(users)} users")
        else:
            print(f"❌ Failed to list users: {response.text}")
        
        # Update user
        print("\n3. Updating test user...")
        update_data = {"role": "editor", "is_active": True}
        response = self.make_request("PATCH", f"/api/admin/users/{user_id}", "admin", json=update_data)
        if response.status_code == 200:
            print("✅ Test user updated successfully")
        else:
            print(f"❌ Failed to update test user: {response.text}")
        
        # Create PAT token
        print("\n4. Creating PAT token...")
        token_data = {
            "name": "test-token",
            "scopes": ["api:read", "rag:read"]
        }
        response = self.make_request("POST", f"/api/admin/users/{user_id}/tokens", "admin", json=token_data)
        if response.status_code == 201:
            print("✅ PAT token created successfully")
            token_info = response.json()
            print(f"   Token: {token_info.get('token_plain_once', 'N/A')[:20]}...")
        else:
            print(f"❌ Failed to create PAT token: {response.text}")
        
        # List audit logs
        print("\n5. Checking audit logs...")
        response = self.make_request("GET", "/api/admin/audit-logs", "admin")
        if response.status_code == 200:
            logs = response.json()["logs"]
            print(f"✅ Found {len(logs)} audit log entries")
        else:
            print(f"❌ Failed to get audit logs: {response.text}")
    
    def test_rag_api(self):
        """Test RAG API with different roles."""
        print("\n📚 Testing RAG API")
        print("=" * 50)
        
        # Test search (should work for all roles)
        print("\n1. Testing RAG search...")
        for role in ["admin", "editor", "reader"]:
            response = self.make_request("POST", "/api/rag/search", role, json={"query": "test"})
            if response.status_code == 200:
                print(f"✅ {role.capitalize()} can search RAG documents")
            else:
                print(f"❌ {role.capitalize()} cannot search RAG documents: {response.status_code}")
        
        # Test stats (should work for all roles)
        print("\n2. Testing RAG stats...")
        for role in ["admin", "editor", "reader"]:
            response = self.make_request("GET", "/api/rag/stats", role)
            if response.status_code == 200:
                print(f"✅ {role.capitalize()} can view RAG stats")
            else:
                print(f"❌ {role.capitalize()} cannot view RAG stats: {response.status_code}")


def setup_test_users():
    """Setup test users in the database."""
    print("🔧 Setting up test users...")
    
    session = next(get_session())
    repo = UsersRepo(session)
    
    try:
        # Create admin user
        if not repo.by_login("admin"):
            repo.create_user(
                login="admin",
                password_hash=hash_password("admin123456"),
                role="admin",
                email="admin@test.com"
            )
            print("✅ Created admin user")
        
        # Create editor user
        if not repo.by_login("editor"):
            repo.create_user(
                login="editor",
                password_hash=hash_password("editor123456"),
                role="editor",
                email="editor@test.com"
            )
            print("✅ Created editor user")
        
        # Create reader user
        if not repo.by_login("reader"):
            repo.create_user(
                login="reader",
                password_hash=hash_password("reader123456"),
                role="reader",
                email="reader@test.com"
            )
            print("✅ Created reader user")
        
    except Exception as e:
        print(f"❌ Error setting up test users: {e}")
    finally:
        session.close()


def main():
    """Main test function."""
    print("🚀 RBAC System Test")
    print("=" * 50)
    
    # Setup test users
    setup_test_users()
    
    # Initialize tester
    tester = RBACTester()
    
    # Login all users
    print("\n🔑 Logging in users...")
    if not all([
        tester.login("admin", "admin123456"),
        tester.login("editor", "editor123456"),
        tester.login("reader", "reader123456")
    ]):
        print("❌ Failed to login all users. Make sure the server is running.")
        return
    
    # Run tests
    tester.test_rbac()
    tester.test_admin_api()
    tester.test_rag_api()
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    main()
