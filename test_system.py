#!/usr/bin/env python3
"""
Быстрый тест системы ML Portal
"""
import requests
import json

def test_api():
    """Тестируем API endpoints"""
    base_url = "http://localhost:8000"
    
    print("🧪 Тестирование ML Portal API...")
    
    # 1. Health check
    print("\n1. Health Check:")
    try:
        response = requests.get(f"{base_url}/healthz", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # 2. OpenAPI docs
    print("\n2. OpenAPI Documentation:")
    try:
        response = requests.get(f"{base_url}/docs", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Available at: {base_url}/docs")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 3. Admin API (should be protected)
    print("\n3. Admin API Protection:")
    try:
        response = requests.get(f"{base_url}/api/admin/users", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        if response.status_code == 401:
            print("   ✅ Admin API properly protected")
        else:
            print("   ⚠️  Admin API not properly protected")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 4. RAG API (should be protected)
    print("\n4. RAG API Protection:")
    try:
        response = requests.get(f"{base_url}/api/rag/search", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✅ RAG API properly protected")
        else:
            print("   ⚠️  RAG API not properly protected")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return True

def test_frontend():
    """Тестируем фронтенд"""
    print("\n🌐 Тестирование Frontend...")
    
    try:
        response = requests.get("http://localhost:3000", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Frontend is accessible")
            return True
        else:
            print(f"   ⚠️  Frontend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Frontend not accessible: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🚀 ML Portal System Test")
    print("=" * 50)
    
    # Тестируем API
    api_ok = test_api()
    
    # Тестируем фронтенд
    frontend_ok = test_frontend()
    
    # Итоги
    print("\n📊 Результаты тестирования:")
    print("=" * 50)
    print(f"API: {'✅ OK' if api_ok else '❌ FAILED'}")
    print(f"Frontend: {'✅ OK' if frontend_ok else '❌ FAILED'}")
    
    if api_ok and frontend_ok:
        print("\n🎉 Система работает! Откройте http://localhost:3000 в браузере")
    else:
        print("\n⚠️  Есть проблемы с системой")

if __name__ == "__main__":
    main()
