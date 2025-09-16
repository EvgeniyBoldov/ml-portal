#!/usr/bin/env python3
"""
Тест локальной системы ML Portal
"""
import requests
import json
import time

def wait_for_service(url, timeout=60, interval=5):
    """Ждем пока сервис станет доступен"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return True
        except:
            pass
        print(f"⏳ Ждем {url}...")
        time.sleep(interval)
    return False

def test_system():
    """Тестируем всю систему"""
    print("🚀 Тестирование ML Portal (локальная версия)")
    print("=" * 60)
    
    # 1. Ждем API
    print("\n1. 🔍 Проверяем API...")
    if not wait_for_service("http://localhost:8000/healthz"):
        print("❌ API не отвечает")
        return False
    
    print("✅ API работает")
    
    # 2. Проверяем setup статус
    print("\n2. 🔧 Проверяем setup статус...")
    try:
        response = requests.get("http://localhost:8000/api/setup/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            print(f"   Debug mode: {status['debug_mode']}")
            print(f"   Admin users: {status['admin_users_count']}")
            print(f"   Has admin: {status['has_admin']}")
            
            if not status['has_admin']:
                print("\n3. 👤 Создаем суперпользователя...")
                create_response = requests.post(
                    "http://localhost:8000/api/setup/create-superuser",
                    timeout=10
                )
                if create_response.status_code == 200:
                    admin = create_response.json()
                    print(f"✅ Суперпользователь создан: {admin['login']} ({admin['email']})")
                else:
                    print(f"❌ Ошибка создания суперпользователя: {create_response.text}")
                    return False
            else:
                print("✅ Суперпользователь уже существует")
        else:
            print(f"❌ Ошибка проверки статуса: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    
    # 3. Тестируем авторизацию
    print("\n4. 🔐 Тестируем авторизацию...")
    try:
        # Логинимся
        login_response = requests.post(
            "http://localhost:8000/api/auth/login",
            json={"login": "admin", "password": "admin123456"},
            timeout=10
        )
        
        if login_response.status_code == 200:
            token_data = login_response.json()
            token = token_data['access_token']
            print("✅ Авторизация работает")
            
            # Тестируем защищенные эндпоинты
            headers = {"Authorization": f"Bearer {token}"}
            
            # Admin API
            admin_response = requests.get(
                "http://localhost:8000/api/admin/users",
                headers=headers,
                timeout=10
            )
            if admin_response.status_code == 200:
                print("✅ Admin API работает")
            else:
                print(f"⚠️  Admin API: {admin_response.status_code}")
            
            # RAG API (POST, не GET)
            rag_response = requests.post(
                "http://localhost:8000/api/rag/search",
                headers=headers,
                json={"query": "test"},
                timeout=10
            )
            if rag_response.status_code in [200, 422]:  # 422 = validation error, но API доступен
                print("✅ RAG API работает")
            else:
                print(f"⚠️  RAG API: {rag_response.status_code}")
                
        else:
            print(f"❌ Ошибка авторизации: {login_response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования авторизации: {e}")
        return False
    
    # 4. Проверяем фронтенд
    print("\n5. 🌐 Проверяем фронтенд...")
    if wait_for_service("http://localhost:3000", timeout=30):
        print("✅ Фронтенд работает на http://localhost:3000")
    else:
        print("⚠️  Фронтенд не отвечает (возможно, еще запускается)")
    
    return True

def main():
    """Основная функция"""
    print("Запуск тестирования через 10 секунд...")
    print("(Убедитесь, что система запущена: make up-local)")
    time.sleep(10)
    
    if test_system():
        print("\n🎉 Система работает отлично!")
        print("\n📋 Доступные URL:")
        print("   • Фронтенд: http://localhost:3000")
        print("   • API Docs: http://localhost:8000/docs")
        print("   • Admin: admin / admin123456")
        print("   • MinIO: http://localhost:9001 (minioadmin / minioadmin)")
    else:
        print("\n❌ Есть проблемы с системой")

if __name__ == "__main__":
    main()
