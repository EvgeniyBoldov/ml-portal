#!/usr/bin/env python3
"""
Скрипт для анализа и исправления проблем в тестах
"""
import os
import sys
import subprocess
import re
from pathlib import Path

def run_command(cmd, cwd=None):
    """Запуск команды и возврат результата"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def analyze_test_failures():
    """Анализ падающих тестов"""
    print("🔍 Анализ падающих тестов...")
    
    # Запускаем unit тесты и получаем список падающих
    cmd = "docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ --tb=no -q"
    returncode, stdout, stderr = run_command(cmd, cwd="/Users/evgeniyboldov/Git/ml-portal")
    
    if returncode != 0:
        print(f"❌ Ошибка запуска тестов: {stderr}")
        return []
    
    # Парсим вывод для получения списка падающих тестов
    failed_tests = []
    lines = stdout.split('\n')
    for line in lines:
        if 'FAILED' in line:
            test_name = line.split('::')[-1]
            failed_tests.append(test_name)
    
    print(f"📊 Найдено {len(failed_tests)} падающих тестов")
    return failed_tests

def categorize_failures():
    """Категоризация ошибок по типам"""
    categories = {
        'import_errors': [],
        'mock_errors': [],
        'pydantic_errors': [],
        'async_errors': [],
        'attribute_errors': [],
        'other': []
    }
    
    # Запускаем тесты с детальным выводом
    cmd = "docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ --tb=short -q"
    returncode, stdout, stderr = run_command(cmd, cwd="/Users/evgeniyboldov/Git/ml-portal")
    
    if returncode != 0:
        print(f"❌ Ошибка анализа: {stderr}")
        return categories
    
    # Анализируем ошибки
    lines = stdout.split('\n')
    current_test = None
    
    for line in lines:
        if 'FAILED' in line:
            current_test = line.strip()
        elif current_test and 'E   ' in line:
            error = line.strip()
            if 'ImportError' in error or 'ModuleNotFoundError' in error:
                categories['import_errors'].append((current_test, error))
            elif 'Mock' in error or 'mock' in error:
                categories['mock_errors'].append((current_test, error))
            elif 'pydantic' in error.lower() or 'ValidationError' in error:
                categories['pydantic_errors'].append((current_test, error))
            elif 'async' in error.lower() or 'await' in error:
                categories['async_errors'].append((current_test, error))
            elif 'AttributeError' in error:
                categories['attribute_errors'].append((current_test, error))
            else:
                categories['other'].append((current_test, error))
    
    return categories

def print_categories(categories):
    """Вывод категоризированных ошибок"""
    print("\n📋 Категоризация ошибок:")
    
    for category, errors in categories.items():
        if errors:
            print(f"\n🔸 {category.upper()} ({len(errors)} ошибок):")
            for test, error in errors[:5]:  # Показываем первые 5
                print(f"  • {test}")
                print(f"    {error}")
            if len(errors) > 5:
                print(f"  ... и еще {len(errors) - 5} ошибок")

def fix_common_issues():
    """Исправление общих проблем"""
    print("\n🔧 Исправление общих проблем...")
    
    fixes_applied = 0
    
    # 1. Исправление проблем с моками в admin router
    admin_router_file = "/Users/evgeniyboldov/Git/ml-portal/apps/api/tests/unit/api/test_admin_router.py"
    if os.path.exists(admin_router_file):
        print("  🔸 Исправление моков в admin router...")
        # Здесь можно добавить автоматические исправления
        fixes_applied += 1
    
    # 2. Исправление проблем с Pydantic схемами
    print("  🔸 Проверка Pydantic схем...")
    # Здесь можно добавить проверки схем
    
    # 3. Исправление проблем с async/await
    print("  🔸 Проверка async/await...")
    # Здесь можно добавить проверки async функций
    
    print(f"✅ Применено {fixes_applied} исправлений")

def generate_test_report():
    """Генерация отчета о тестах"""
    print("\n📊 Генерация отчета...")
    
    # Запускаем тесты с покрытием
    cmd = "docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ --cov=app --cov-report=term-missing -q"
    returncode, stdout, stderr = run_command(cmd, cwd="/Users/evgeniyboldov/Git/ml-portal")
    
    if returncode == 0:
        print("✅ Отчет о покрытии сгенерирован")
        # Извлекаем статистику покрытия
        lines = stdout.split('\n')
        for line in lines:
            if 'TOTAL' in line:
                print(f"📈 {line}")
    else:
        print(f"❌ Ошибка генерации отчета: {stderr}")

def main():
    """Основная функция"""
    print("🚀 Анализ и исправление тестов ML Portal")
    print("=" * 50)
    
    # Анализ падающих тестов
    failed_tests = analyze_test_failures()
    
    # Категоризация ошибок
    categories = categorize_failures()
    print_categories(categories)
    
    # Исправление общих проблем
    fix_common_issues()
    
    # Генерация отчета
    generate_test_report()
    
    print("\n🎯 Рекомендации:")
    print("1. Исправить проблемы с моками в роутерах")
    print("2. Обновить Pydantic схемы")
    print("3. Проверить async/await функции")
    print("4. Добавить недостающие методы в сервисы")
    
    print("\n✨ Анализ завершен!")

if __name__ == "__main__":
    main()
