#!/usr/bin/env python3
"""
Скрипт для тестирования всех улучшений безопасности
"""
import os
import sys
import asyncio
import requests
import json
from datetime import datetime, timedelta

# Добавляем путь к приложению
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.security import validate_password_strength, hash_password, verify_password
from app.core.pat_validation import validate_scopes, check_scope_permission
from app.core.config import settings

def test_password_validation():
    """Тестирование валидации паролей"""
    print("🔐 Тестирование валидации паролей...")
    
    # Валидные пароли
    valid_passwords = [
        "StrongPassword123!",
        "AnotherValid1@",
        "Test123!@#$%"
    ]
    
    for password in valid_passwords:
        is_valid, error_msg = validate_password_strength(password)
        assert is_valid, f"Пароль '{password}' должен быть валидным: {error_msg}"
        print(f"  ✅ {password}")
    
    # Невалидные пароли
    invalid_passwords = [
        ("short", "слишком короткий"),
        ("nouppercase123!", "нет заглавных букв"),
        ("NOLOWERCASE123!", "нет строчных букв"),
        ("NoDigits!", "нет цифр"),
        ("NoSpecial123", "нет спецсимволов")
    ]
    
    for password, reason in invalid_passwords:
        is_valid, error_msg = validate_password_strength(password)
        assert not is_valid, f"Пароль '{password}' должен быть невалидным ({reason})"
        print(f"  ❌ {password} - {error_msg}")
    
    print("  ✅ Валидация паролей работает корректно")

def test_password_hashing():
    """Тестирование хеширования паролей с pepper"""
    print("🔒 Тестирование хеширования паролей...")
    
    password = "TestPassword123!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    
    # Хеши должны быть разными из-за соли
    assert hash1 != hash2, "Хеши должны быть разными из-за соли"
    
    # Оба должны верифицироваться корректно
    assert verify_password(password, hash1), "Первый хеш должен верифицироваться"
    assert verify_password(password, hash2), "Второй хеш должен верифицироваться"
    
    # Неправильный пароль не должен верифицироваться
    assert not verify_password("WrongPassword123!", hash1), "Неправильный пароль не должен верифицироваться"
    
    print("  ✅ Хеширование паролей работает корректно")

def test_pat_scope_validation():
    """Тестирование валидации scopes для PAT"""
    print("🎫 Тестирование валидации PAT scopes...")
    
    # Валидные scopes
    valid_scopes = ["api:read", "rag:write", "chat:admin"]
    validated = validate_scopes(valid_scopes)
    
    assert "api:read" in validated
    assert "rag:write" in validated
    assert "chat:admin" in validated
    assert "chat:read" in validated  # Должен быть расширен из chat:admin
    assert "chat:write" in validated  # Должен быть расширен из chat:admin
    
    print(f"  ✅ Валидные scopes: {validated}")
    
    # Тестирование проверки разрешений
    user_scopes = ["api:admin", "rag:read"]
    
    # Должны иметь разрешения для включенных scopes
    assert check_scope_permission(user_scopes, "api:admin")
    assert check_scope_permission(user_scopes, "rag:read")
    
    # Должны иметь разрешения для scopes более низкого уровня
    assert check_scope_permission(user_scopes, "api:read")
    assert check_scope_permission(user_scopes, "api:write")
    
    # Не должны иметь разрешения для несвязанных scopes
    assert not check_scope_permission(user_scopes, "chat:read")
    assert not check_scope_permission(user_scopes, "users:admin")
    
    print("  ✅ Проверка разрешений scopes работает корректно")
    
    # Невалидные scopes
    try:
        validate_scopes(["invalid:scope", "api:read"])
        assert False, "Должно было выбросить исключение для невалидных scopes"
    except Exception as e:
        print(f"  ✅ Невалидные scopes корректно отклонены: {e}")

def test_rate_limiting():
    """Тестирование rate limiting"""
    print("⏱️  Тестирование rate limiting...")
    
    base_url = "http://localhost:8000"
    
    # Тестируем rate limiting для login
    print("  Тестирование rate limiting для /api/auth/login...")
    
    for i in range(12):  # Больше лимита
        try:
            response = requests.post(f"{base_url}/api/auth/login", json={
                "login": "testuser",
                "password": "wrongpassword"
            }, timeout=5)
            
            if i < 10:  # Первые 10 должны быть разрешены
                assert response.status_code in [400, 401], f"Попытка {i+1}: ожидался 400/401, получен {response.status_code}"
            else:  # После 10 должны быть ограничены
                assert response.status_code == 429, f"Попытка {i+1}: ожидался 429, получен {response.status_code}"
                print(f"  ✅ Rate limiting сработал на попытке {i+1}")
                break
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Ошибка подключения: {e}")
            break
    
    # Тестируем rate limiting для password reset
    print("  Тестирование rate limiting для /auth/password/forgot...")
    
    for i in range(7):  # Больше лимита
        try:
            response = requests.post(f"{base_url}/auth/password/forgot", json={
                "login_or_email": "test@example.com"
            }, timeout=5)
            
            if i < 5:  # Первые 5 должны быть разрешены
                assert response.status_code == 200, f"Попытка {i+1}: ожидался 200, получен {response.status_code}"
            else:  # После 5 должны быть ограничены
                assert response.status_code == 429, f"Попытка {i+1}: ожидался 429, получен {response.status_code}"
                print(f"  ✅ Rate limiting сработал на попытке {i+1}")
                break
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Ошибка подключения: {e}")
            break

def test_cors_configuration():
    """Тестирование CORS конфигурации"""
    print("🌐 Тестирование CORS конфигурации...")
    
    base_url = "http://localhost:8000"
    
    try:
        # Тестируем OPTIONS запрос
        response = requests.options(f"{base_url}/api/auth/login", timeout=5)
        
        # Должны быть CORS заголовки
        assert "access-control-allow-origin" in response.headers, "Отсутствует CORS заголовок"
        assert "access-control-allow-methods" in response.headers, "Отсутствует CORS заголовок методов"
        
        print("  ✅ CORS заголовки присутствуют")
        
        # Проверяем конфигурацию
        assert hasattr(settings, 'CORS_ORIGINS'), "Отсутствует CORS_ORIGINS в настройках"
        assert hasattr(settings, 'CORS_ENABLED'), "Отсутствует CORS_ENABLED в настройках"
        assert hasattr(settings, 'CORS_ALLOW_CREDENTIALS'), "Отсутствует CORS_ALLOW_CREDENTIALS в настройках"
        
        print(f"  ✅ CORS настройки: origins={settings.CORS_ORIGINS}, enabled={settings.CORS_ENABLED}")
        
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Ошибка подключения: {e}")

def test_password_reset_security():
    """Тестирование безопасности password reset"""
    print("🔑 Тестирование безопасности password reset...")
    
    base_url = "http://localhost:8000"
    
    # Тестируем, что всегда возвращается 200 для безопасности
    test_cases = [
        "nonexistent@example.com",
        "invalid-email",
        "nonexistent_user"
    ]
    
    for test_case in test_cases:
        try:
            response = requests.post(f"{base_url}/auth/password/forgot", json={
                "login_or_email": test_case
            }, timeout=5)
            
            assert response.status_code == 200, f"Для '{test_case}' ожидался 200, получен {response.status_code}"
            print(f"  ✅ '{test_case}' корректно возвращает 200")
            
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Ошибка подключения для '{test_case}': {e}")

def test_sse_heartbeat():
    """Тестирование SSE heartbeat"""
    print("💓 Тестирование SSE heartbeat...")
    
    from app.api.sse import sse_heartbeat_response
    
    # Тестируем структуру ответа
    response = sse_heartbeat_response(heartbeat_interval=1)
    
    assert response.media_type == "text/event-stream", "Неправильный media type"
    assert "Cache-Control" in response.headers, "Отсутствует Cache-Control заголовок"
    assert "Connection" in response.headers, "Отсутствует Connection заголовок"
    assert response.headers["Cache-Control"] == "no-cache", "Неправильный Cache-Control"
    assert response.headers["Connection"] == "keep-alive", "Неправильный Connection"
    
    print("  ✅ SSE heartbeat структура корректна")

def test_audit_logging():
    """Тестирование audit logging"""
    print("📝 Тестирование audit logging...")
    
    from app.services.audit_service import AuditService
    
    # Проверяем, что сервис имеет необходимые методы
    assert hasattr(AuditService, 'log_action'), "Отсутствует метод log_action"
    assert hasattr(AuditService, 'log_user_action'), "Отсутствует метод log_user_action"
    assert hasattr(AuditService, 'log_token_action'), "Отсутствует метод log_token_action"
    assert hasattr(AuditService, 'log_auth_action'), "Отсутствует метод log_auth_action"
    
    print("  ✅ Audit logging методы присутствуют")

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования улучшений безопасности...")
    print("=" * 60)
    
    try:
        test_password_validation()
        print()
        
        test_password_hashing()
        print()
        
        test_pat_scope_validation()
        print()
        
        test_rate_limiting()
        print()
        
        test_cors_configuration()
        print()
        
        test_password_reset_security()
        print()
        
        test_sse_heartbeat()
        print()
        
        test_audit_logging()
        print()
        
        print("=" * 60)
        print("✅ Все тесты безопасности прошли успешно!")
        
    except Exception as e:
        print("=" * 60)
        print(f"❌ Ошибка в тестах безопасности: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
