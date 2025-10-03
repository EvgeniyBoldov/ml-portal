from locust import HttpUser, task, between
import json
import random

class MLPortalUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts"""
        self.login()
    
    def login(self):
        """Login and get authentication token"""
        login_data = {
            "email": "test@example.com",
            "password": "TestPassword123!"
        }
        
        with self.client.post("/api/v1/auth/login", json=login_data, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                response.success()
            else:
                response.failure(f"Login failed with status {response.status_code}")
    
    @task(3)
    def get_health(self):
        """Test health endpoint"""
        with self.client.get("/api/v1/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed with status {response.status_code}")
    
    @task(2)
    def get_users(self):
        """Test users endpoint"""
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.get("/api/v1/users", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get users failed with status {response.status_code}")
    
    @task(2)
    def get_chats(self):
        """Test chats endpoint"""
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.get("/api/v1/chats", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get chats failed with status {response.status_code}")
    
    @task(1)
    def create_chat(self):
        """Test creating a chat"""
        headers = {"Authorization": f"Bearer {self.token}"}
        chat_data = {
            "name": f"Test Chat {random.randint(1, 1000)}",
            "description": "Performance test chat"
        }
        
        with self.client.post("/api/v1/chats", json=chat_data, headers=headers, catch_response=True) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Create chat failed with status {response.status_code}")
    
    @task(1)
    def get_rag_documents(self):
        """Test RAG documents endpoint"""
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.get("/api/v1/rag/documents", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get RAG documents failed with status {response.status_code}")
    
    @task(1)
    def search_rag(self):
        """Test RAG search endpoint"""
        headers = {"Authorization": f"Bearer {self.token}"}
        search_data = {
            "query": "machine learning",
            "limit": 10
        }
        
        with self.client.post("/api/v1/rag/search", json=search_data, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"RAG search failed with status {response.status_code}")
    
    @task(1)
    def get_tenants(self):
        """Test tenants endpoint"""
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.get("/api/v1/tenants", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get tenants failed with status {response.status_code}")
    
    @task(1)
    def get_admin_status(self):
        """Test admin status endpoint"""
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.get("/api/v1/admin/status", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get admin status failed with status {response.status_code}")
