#!/usr/bin/env python3
"""
Скрипт для запуска E2E тестов всей системы
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

def run_command(cmd, timeout=300):
    """Выполняет команду с таймаутом"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, timeout=timeout)
        return True, result.stdout
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout} seconds"
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except Exception as e:
        return False, str(e)

def check_service_health(service_name, url, max_retries=30):
    """Проверяет здоровье сервиса"""
    print(f"🔍 Проверка {service_name}...")
    
    for i in range(max_retries):
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    print(f"✅ {service_name} готов")
                    return True
        except:
            pass
        
        print(f"⏳ Ожидание {service_name}... ({i+1}/{max_retries})")
        time.sleep(2)
    
    print(f"❌ {service_name} не готов")
    return False

def main():
    """Основная функция запуска тестов"""
    print("🚀 Запуск E2E тестов ML Portal")
    print("=" * 50)
    
    # 1. Проверяем, что Docker запущен
    print("\n1. Проверка Docker...")
    success, output = run_command("docker --version")
    if not success:
        print("❌ Docker не установлен или не запущен")
        return 1
    print("✅ Docker готов")
    
    # 2. Собираем образы
    print("\n2. Сборка образов...")
    success, output = run_command("make build-local")
    if not success:
        print(f"❌ Ошибка сборки: {output}")
        return 1
    print("✅ Образы собраны")
    
    # 3. Запускаем сервисы
    print("\n3. Запуск сервисов...")
    success, output = run_command("make up-local")
    if not success:
        print(f"❌ Ошибка запуска: {output}")
        return 1
    print("✅ Сервисы запущены")
    
    # 4. Инициализируем MinIO
    print("\n4. Инициализация MinIO...")
    success, output = run_command("make init-models")
    if not success:
        print(f"⚠️  Предупреждение инициализации MinIO: {output}")
    else:
        print("✅ MinIO инициализирован")
    
    # 5. Ждем готовности сервисов
    print("\n5. Ожидание готовности сервисов...")
    
    services = [
        ("API", "http://localhost:8000/health"),
        ("PostgreSQL", "http://localhost:8000/health"),  # Проверяем через API
        ("Redis", "http://localhost:8000/health"),
        ("Qdrant", "http://localhost:8000/health"),
        ("MinIO", "http://localhost:8000/health")
    ]
    
    all_ready = True
    for service_name, url in services:
        if not check_service_health(service_name, url):
            all_ready = False
    
    if not all_ready:
        print("❌ Не все сервисы готовы")
        return 1
    
    print("✅ Все сервисы готовы")
    
    # 6. Запускаем тесты
    print("\n6. Запуск E2E тестов...")
    
    # Устанавливаем зависимости для тестов
    print("📦 Установка зависимостей для тестов...")
    success, output = run_command("pip install httpx pytest pytest-asyncio")
    if not success:
        print(f"⚠️  Предупреждение установки зависимостей: {output}")
    
    # Запускаем тесты
    test_cmd = "cd backend && python -m pytest tests/e2e/test_full_system.py -v -s --tb=short"
    success, output = run_command(test_cmd, timeout=600)  # 10 минут на тесты
    
    if success:
        print("✅ Все тесты прошли успешно!")
        print("\n📊 Результаты тестов:")
        print(output)
    else:
        print("❌ Некоторые тесты не прошли")
        print("\n📊 Результаты тестов:")
        print(output)
        return 1
    
    # 7. Очистка (опционально)
    print("\n7. Очистка...")
    response = input("Остановить сервисы? (y/N): ").strip().lower()
    if response in ['y', 'yes', 'да']:
        success, output = run_command("make down-local")
        if success:
            print("✅ Сервисы остановлены")
        else:
            print(f"⚠️  Ошибка остановки: {output}")
    
    print("\n🎉 E2E тесты завершены!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
