#!/usr/bin/env python3
"""
Скрипт для генерации кода тестов.
Создает tests-code.txt с полными путями от корня проекта.
"""

import os
import sys
from pathlib import Path
from typing import List, Set

# Расширения файлов для тестов
TEST_EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx', '.spec.ts', '.spec.js', '.test.ts', '.test.js'
}

# Файлы и директории для исключения
EXCLUDE_PATTERNS = {
    'node_modules', '__pycache__', '.git', '.venv', '.env',
    'dist', 'build', '.pytest_cache', '.cache', '.vscode',
    '.idea', '.DS_Store', '*.pyc', '*.pyo', '*.pyd',
    '*.tsbuildinfo', '*.log', '*.tmp', '*.temp', 'migrations',
    'coverage', 'test-results', 'playwright-report'
}

# Файлы для исключения по имени
EXCLUDE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    '*.min.js', '*.min.css', '*.bundle.js', 'alembic.ini'
}

def should_include_file(file_path: Path, extensions: Set[str]) -> bool:
    """Проверяет, нужно ли включать файл в генерацию."""
    
    # Проверяем расширение
    if file_path.suffix.lower() not in extensions:
        return False
    
    # Проверяем исключаемые паттерны в пути
    path_str = str(file_path).lower()
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_str:
            return False
    
    # Проверяем исключаемые файлы
    for pattern in EXCLUDE_FILES:
        if file_path.name == pattern or file_path.name.endswith(pattern.replace('*', '')):
            return False
    
    return True

def is_test_file(file_path: Path) -> bool:
    """Проверяет, является ли файл тестовым."""
    name = file_path.name.lower()
    return (
        'test' in name or 
        'spec' in name or 
        file_path.parent.name == 'tests' or
        file_path.parent.name == 'test' or
        file_path.parent.name == '__tests__' or
        file_path.parent.name == 'e2e-tests'
    )

def read_file_content(file_path: Path, project_root: Path) -> str:
    """Читает содержимое файла с обработкой ошибок."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
            return f"# WARNING: File contains non-UTF-8 content, decoded as latin-1\n{content}"
        except Exception as e:
            return f"# ERROR: Could not read file - {e}"
    except Exception as e:
        return f"# ERROR: Could not read file - {e}"

def generate_tests_for_directory(
    directory: Path, 
    project_root: Path, 
    output_lines: List[str], 
    extensions: Set[str],
    component_type: str
) -> None:
    """Рекурсивно генерирует код тестов для директории."""
    
    if not directory.exists() or not directory.is_dir():
        return
    
    # Получаем все файлы и директории, отсортированные по имени
    items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    
    for item in items:
        if item.is_file() and should_include_file(item, extensions) and is_test_file(item):
            # Вычисляем полный путь от корня проекта
            full_path = item.relative_to(project_root)
            path_str = str(full_path).replace('\\', '/')  # Нормализуем пути
            
            output_lines.append(f"\n{'#' * 80}")
            output_lines.append(f"# {path_str}")
            output_lines.append(f"{'#' * 80}")
            
            content = read_file_content(item, project_root)
            if content.strip():
                output_lines.append(content)
            else:
                output_lines.append("# (empty file)")
                
        elif item.is_dir() and not any(pattern in str(item) for pattern in EXCLUDE_PATTERNS):
            # Рекурсивно обрабатываем поддиректории
            generate_tests_for_directory(item, project_root, output_lines, extensions, component_type)

def generate_tests_code(project_root: Path) -> str:
    """Генерирует код тестов."""
    output_lines = []
    
    output_lines.append("ML Portal - Tests Code")
    output_lines.append("=" * 50)
    output_lines.append(f"Generated from: {project_root}")
    output_lines.append(f"Component: Tests (all test files)")
    output_lines.append("")
    
    # Обрабатываем тесты бэкенда
    backend_tests_dir = project_root / "apps" / "api" / "tests"
    if backend_tests_dir.exists():
        output_lines.append(f"\n{'=' * 60}")
        output_lines.append("# BACKEND TESTS")
        output_lines.append(f"{'=' * 60}")
        generate_tests_for_directory(backend_tests_dir, project_root, output_lines, TEST_EXTENSIONS, "backend_tests")
    
    # Обрабатываем тесты фронтенда
    frontend_tests_dir = project_root / "apps" / "web" / "e2e-tests"
    if frontend_tests_dir.exists():
        output_lines.append(f"\n{'=' * 60}")
        output_lines.append("# FRONTEND E2E TESTS")
        output_lines.append(f"{'=' * 60}")
        generate_tests_for_directory(frontend_tests_dir, project_root, output_lines, TEST_EXTENSIONS, "frontend_tests")
    
    # Обрабатываем другие тестовые файлы в проекте
    for test_dir in ["tests", "test", "__tests__"]:
        test_path = project_root / test_dir
        if test_path.exists():
            output_lines.append(f"\n{'=' * 60}")
            output_lines.append(f"# {test_dir.upper()} TESTS")
            output_lines.append(f"{'=' * 60}")
            generate_tests_for_directory(test_path, project_root, output_lines, TEST_EXTENSIONS, "general_tests")
    
    return "\n".join(output_lines)

def main():
    """Основная функция."""
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path(__file__).parent.parent.parent.resolve()
    
    print(f"Generating tests code from: {project_root}")
    
    # Создаем директорию для выходных файлов
    output_dir = project_root / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем код тестов
    print("Generating tests code...")
    tests_code = generate_tests_code(project_root)
    tests_file = output_dir / "tests-code.txt"
    with open(tests_file, 'w', encoding='utf-8') as f:
        f.write(tests_code)
    print(f"Tests code written to: {tests_file}")
    
    print("Tests code generation complete!")

if __name__ == "__main__":
    main()
