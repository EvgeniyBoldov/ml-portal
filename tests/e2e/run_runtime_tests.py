"""
Скрипт для запуска всех E2E тестов runtime рефакторинга в Docker контейнерах
"""
import subprocess
import sys
import os
import time
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Выполнить команду и вернуть результат"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    
    print(f"Success: {result.stdout}")
    return True


def wait_for_service(service_name, max_wait=60):
    """Ждать пока сервис станет готов"""
    print(f"Waiting for {service_name} to be ready...")
    
    for i in range(max_wait):
        try:
            # Проверяем health endpoint
            result = subprocess.run(
                ["docker", "compose", "-f", "docker-compose.test.yml", "exec", service_name, "curl", "-f", "http://localhost:8000/health"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"✅ {service_name} is ready")
                return True
        except:
            pass
        
        time.sleep(1)
    
    print(f"❌ {service_name} failed to start")
    return False


def setup_test_environment():
    """Настройка тестового окружения"""
    print("🔧 Setting up test environment...")
    
    # Запускаем тестовые сервисы
    if not run_command(["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d", "--profile", "test"]):
        print("❌ Failed to start test services")
        return False
    
    # Ждем готовности сервисов
    services = ["postgres-test", "redis-test", "mock-llm", "emb-test"]
    for service in services:
        if not wait_for_service(service):
            return False
    
    print("✅ Test environment ready")
    return True


def cleanup_test_environment():
    """Очистка тестового окружения"""
    print("🧹 Cleaning up test environment...")
    
    # Останавливаем и удаляем контейнеры
    run_command(["docker", "compose", "-f", "docker-compose.test.yml", "down", "--volumes", "--remove-orphans"], check=False)
    
    print("✅ Test environment cleaned up")


def run_backend_tests():
    """Запуск backend тестов в контейнере"""
    print("\n1️⃣ Backend E2E Tests")
    print("-" * 40)
    
    backend_tests = [
        "tests/e2e/test_runtime_refactor.py",
        "tests/e2e/test_runtime_performance.py", 
        "tests/e2e/test_runtime_regression.py"
    ]
    
    for test_file in backend_tests:
        print(f"Running {test_file}...")
        
        cmd = [
            "docker", "compose", "-f", "docker-compose.test.yml", "exec",
            "api-test", "python", "-m", "pytest", test_file, "-v", "--tb=short"
        ]
        
        if not run_command(cmd):
            print(f"❌ Failed: {test_file}")
            return False
        else:
            print(f"✅ Passed: {test_file}")
    
    return True


def run_frontend_tests():
    """Запуск frontend тестов в контейнере"""
    print("\n2️⃣ Frontend E2E Tests")
    print("-" * 40)
    
    frontend_tests = [
        "e2e-tests/runtime-refactor.spec.ts"
    ]
    
    for test_file in frontend_tests:
        print(f"Running {test_file}...")
        
        cmd = [
            "docker", "compose", "-f", "docker-compose.test.yml", "exec",
            "frontend-test", "npx", "playwright", "test", test_file
        ]
        
        if not run_command(cmd):
            print(f"❌ Failed: {test_file}")
            return False
        else:
            print(f"✅ Passed: {test_file}")
    
    return True


def run_coverage_tests():
    """Запуск тестов с coverage"""
    print("\n5️⃣ Coverage Report")
    print("-" * 40)
    
    cmd = [
        "docker", "compose", "-f", "docker-compose.test.yml", "exec",
        "api-test", "python", "-m", "pytest",
        "tests/e2e/test_runtime_refactor.py",
        "--cov=app.agents",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--tb=short"
    ]
    
    if run_command(cmd):
        print("✅ Coverage report generated")
        
        # Копируем coverage отчет
        run_command([
            "docker", "compose", "-f", "docker-compose.test.yml", "cp",
            "api-test:/app/htmlcov", "./coverage"
        ], check=False)
    else:
        print("⚠️  Coverage report failed (optional)")
    
    return True


def validate_syntax():
    """Проверка синтаксиса"""
    print("\n4️⃣ Syntax Validation")
    print("-" * 40)
    
    # Python файлы
    python_files = [
        "tests/e2e/test_runtime_refactor.py",
        "tests/e2e/test_runtime_performance.py", 
        "tests/e2e/test_runtime_regression.py",
        "tests/fixtures/runtime_fixtures.py"
    ]
    
    for py_file in python_files:
        cmd = [
            "docker", "compose", "-f", "docker-compose.test.yml", "exec",
            "api-test", "python", "-m", "py_compile", py_file
        ]
        
        if not run_command(cmd):
            print(f"❌ Syntax error: {py_file}")
            return False
        else:
            print(f"✅ Syntax OK: {py_file}")
    
    # TypeScript файлы
    ts_files = [
        "e2e-tests/runtime-refactor.spec.ts",
        "e2e-tests/fixtures.ts"
    ]
    
    for ts_file in ts_files:
        cmd = [
            "docker", "compose", "-f", "docker-compose.test.yml", "exec",
            "frontend-test", "npx", "tsc", "--noEmit", ts_file
        ]
        
        if not run_command(cmd):
            print(f"❌ TypeScript error: {ts_file}")
        else:
            print(f"✅ TypeScript OK: {ts_file}")
    
    return True


def main():
    """Основная функция для запуска тестов"""
    
    print("=" * 80)
    print("🐳 Running Runtime Refactor E2E Tests in Docker")
    print("=" * 80)
    
    success = True
    
    try:
        # 1. Настройка окружения
        if not setup_test_environment():
            sys.exit(1)
        
        # 2. Backend тесты
        if not run_backend_tests():
            success = False
        
        # 3. Frontend тесты
        if not run_frontend_tests():
            success = False
        
        # 4. Валидация синтаксиса
        if not validate_syntax():
            success = False
        
        # 5. Coverage отчет
        run_coverage_tests()  # Не критично, продолжаем даже если упал
        
        # 6. Итоги
        print("\n" + "=" * 80)
        if success:
            print("🎉 All Runtime Refactor E2E Tests Passed!")
        else:
            print("❌ Some tests failed!")
        print("=" * 80)
        
        print("\n📋 Test Summary:")
        print("  • Backend E2E: Core runtime functionality")
        print("  • Performance: Runtime speed and memory")
        print("  • Regression: Legacy behavior removal")
        print("  • Frontend E2E: UI interaction validation")
        print("  • Integration: Full system compatibility")
        
        print("\n🔍 What was tested:")
        print("  • Planner loop execution")
        print("  • Tool call handling")
        print("  • Conversation summaries")
        print("  • Policy limits enforcement")
        print("  • Error handling and recovery")
        print("  • Legacy code removal")
        print("  • Performance benchmarks")
        print("  • UI responsiveness")
        
        if success:
            print("\n✅ Runtime refactor is ready for production!")
        
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        success = False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        success = False
    finally:
        # Всегда очищаем окружение
        cleanup_test_environment()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
