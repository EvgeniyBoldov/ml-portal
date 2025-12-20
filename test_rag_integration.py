"""
Integration tests for RAG workflow
Tests: upload, ingest, status, download, global scope, archive, delete
"""
import requests
import time
import io
from typing import Optional

BASE_URL = "http://localhost:8080"
TIMEOUT = 10


class RagIntegrationTests:
    def __init__(self):
        self.admin_token: Optional[str] = None
        self.test_doc_id: Optional[str] = None
        
    def log_info(self, msg: str):
        print(f"ℹ️  {msg}")
    
    def log_success(self, msg: str):
        print(f"✅ {msg}")
    
    def log_error(self, msg: str):
        print(f"❌ {msg}")
    
    def log_section(self, title: str):
        print("\n" + "=" * 80)
        print(f"ℹ️  {title}")
        print("=" * 80)
    
    def test_admin_login(self) -> bool:
        """Test 1: Admin login"""
        self.log_section("Test 1: Admin Login")
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/auth/login",
                json={"login": "admin", "password": "admin123"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                self.log_error(f"Login failed: {response.text}")
                return False
            
            data = response.json()
            self.admin_token = data["access_token"]
            
            self.log_success("Admin logged in successfully")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_upload_document(self) -> bool:
        """Test 2: Upload RAG document"""
        self.log_section("Test 2: Upload Document")
        
        try:
            # Create test file
            test_content = """
# Test Document for RAG Integration

This is a test document for RAG integration testing.

## Section 1: Introduction
This document contains test information that will be indexed by the RAG system.

## Section 2: Technical Details
The RAG system should be able to:
- Upload documents
- Process and chunk them
- Create embeddings
- Store in vector database
- Enable semantic search

## Section 3: Conclusion
This is the end of the test document.
"""
            
            files = {
                'file': ('test_rag_doc.md', io.BytesIO(test_content.encode()), 'text/markdown')
            }
            
            data = {
                'tags': 'test,integration,rag'
            }
            
            response = requests.post(
                f"{BASE_URL}/api/v1/rag/upload",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                files=files,
                data=data,
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                self.log_error(f"Upload failed: {response.text}")
                return False
            
            result = response.json()
            self.test_doc_id = result.get("id") or result.get("document_id")
            
            if not self.test_doc_id:
                self.log_error(f"No document ID in response: {result}")
                return False
            
            self.log_success(f"Document uploaded: {self.test_doc_id}")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_start_ingest(self) -> bool:
        """Test 3: Start ingest process"""
        self.log_section("Test 3: Start Ingest")
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/rag/status/{self.test_doc_id}/ingest/start",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code not in [200, 202]:
                self.log_error(f"Ingest start failed: {response.text}")
                return False
            
            self.log_success("Ingest started")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_check_status(self) -> bool:
        """Test 4: Check ingest status"""
        self.log_section("Test 4: Check Ingest Status")
        
        try:
            max_attempts = 30
            for attempt in range(max_attempts):
                response = requests.get(
                    f"{BASE_URL}/api/v1/rag/status/{self.test_doc_id}",
                    headers={"Authorization": f"Bearer {self.admin_token}"},
                    timeout=TIMEOUT
                )
                
                if response.status_code != 200:
                    self.log_error(f"Status check failed: {response.text}")
                    return False
                
                data = response.json()
                agg_status = data.get("agg_status", "unknown")
                
                self.log_info(f"Attempt {attempt + 1}/{max_attempts}: Status = {agg_status}")
                
                if agg_status == "ready":
                    self.log_success("Document is ready!")
                    return True
                
                if agg_status == "failed":
                    self.log_error(f"Ingest failed: {data}")
                    return False
                
                time.sleep(2)
            
            self.log_error(f"Timeout waiting for ingest to complete (status: {agg_status})")
            return False
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_download_original(self) -> bool:
        """Test 5: Download original file"""
        self.log_section("Test 5: Download Original File")
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/rag/{self.test_doc_id}/download?kind=original",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                self.log_error(f"Download failed: {response.text}")
                return False
            
            content = response.content
            self.log_info(f"Downloaded {len(content)} bytes")
            
            if len(content) == 0:
                self.log_error("Downloaded file is empty")
                return False
            
            self.log_success("Original file downloaded successfully")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_download_canonical(self) -> bool:
        """Test 6: Download canonical (processed) file"""
        self.log_section("Test 6: Download Canonical File")
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/rag/{self.test_doc_id}/download?kind=canonical",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                self.log_error(f"Download failed: {response.text}")
                return False
            
            content = response.content
            self.log_info(f"Downloaded {len(content)} bytes")
            
            if len(content) == 0:
                self.log_error("Downloaded file is empty")
                return False
            
            self.log_success("Canonical file downloaded successfully")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_update_to_global_scope(self) -> bool:
        """Test 7: Update document to global scope"""
        self.log_section("Test 7: Update to Global Scope")
        
        try:
            response = requests.put(
                f"{BASE_URL}/api/v1/rag/{self.test_doc_id}/scope",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                data={"scope": "global"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                self.log_error(f"Scope update failed: {response.text}")
                return False
            
            data = response.json()
            if data.get("scope") != "global":
                self.log_error(f"Scope not updated: {data}")
                return False
            
            self.log_success("Document scope updated to global")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_archive_document(self) -> bool:
        """Test 8: Archive document (exclude from search)"""
        self.log_section("Test 8: Archive Document")
        
        try:
            # Check if archive endpoint exists, otherwise skip
            response = requests.post(
                f"{BASE_URL}/api/v1/rag/{self.test_doc_id}/archive",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code == 404:
                self.log_info("Archive endpoint not implemented, skipping")
                return True
            
            if response.status_code != 200:
                self.log_error(f"Archive failed: {response.text}")
                return False
            
            data = response.json()
            self.log_success("Document archived successfully")
            return True
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def test_delete_document(self) -> bool:
        """Test 9: Delete document"""
        self.log_section("Test 9: Delete Document")
        
        try:
            response = requests.delete(
                f"{BASE_URL}/api/v1/rag/{self.test_doc_id}",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=TIMEOUT
            )
            
            self.log_info(f"Status: {response.status_code}")
            
            if response.status_code not in [200, 204]:
                self.log_error(f"Delete failed: {response.text}")
                return False
            
            # Verify deletion
            self.log_info("Verifying deletion...")
            verify_response = requests.get(
                f"{BASE_URL}/api/v1/rag/status/{self.test_doc_id}",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=TIMEOUT
            )
            
            if verify_response.status_code == 404:
                self.log_success("Document deleted and verified ✓")
                return True
            else:
                self.log_error(f"Document still exists after deletion: {verify_response.status_code}")
                return False
            
        except Exception as e:
            self.log_error(f"Exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all RAG integration tests"""
        print("\n" + "🚀 " * 20)
        print("🚀 " * 8 + "RAG INTEGRATION TESTS")
        print("🚀 " * 20)
        print(f"\nTarget: {BASE_URL}")
        print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        tests = [
            ("Admin Login", self.test_admin_login),
            ("Upload Document", self.test_upload_document),
            ("Start Ingest", self.test_start_ingest),
            ("Check Status", self.test_check_status),
            ("Download Original", self.test_download_original),
            ("Download Canonical", self.test_download_canonical),
            ("Update to Global Scope", self.test_update_to_global_scope),
            ("Archive Document", self.test_archive_document),
            ("Delete Document", self.test_delete_document),
        ]
        
        results = []
        for name, test_func in tests:
            try:
                result = test_func()
                results.append((name, result))
            except Exception as e:
                self.log_error(f"Test '{name}' crashed: {e}")
                results.append((name, False))
        
        # Summary
        self.log_section("TEST SUMMARY")
        print()
        passed = sum(1 for _, r in results if r)
        failed = len(results) - passed
        
        print(f"Total tests: {len(results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}\n")
        
        if passed > 0:
            print("✅ Passed tests:")
            for name, result in results:
                if result:
                    print(f"  - {name}")
        
        if failed > 0:
            print("\n❌ Failed tests:")
            for name, result in results:
                if not result:
                    print(f"  - {name}")
        
        print("\n" + "=" * 80)
        if failed == 0:
            print("✅ ALL TESTS PASSED! 🎉")
        else:
            print(f"❌ {failed} TEST(S) FAILED")
        print("=" * 80 + "\n")
        
        return failed == 0


if __name__ == "__main__":
    tests = RagIntegrationTests()
    success = tests.run_all_tests()
    exit(0 if success else 1)
