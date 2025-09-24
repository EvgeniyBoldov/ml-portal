#!/usr/bin/env python3
"""
Скрипт для генерации всего кода проекта в один txt файл
Разделяет код по категориям: инфраструктура, тесты, бэкенд, фронтенд
"""

import os
import glob
from pathlib import Path
from datetime import datetime

# Конфигурация путей
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "docs" / "generated"
OUTPUT_FILE = OUTPUT_DIR / "full_code.txt"

# Расширения файлов для разных категорий
CODE_EXTENSIONS = {
    'python': ['.py'],
    'javascript': ['.js', '.jsx', '.ts', '.tsx'],
    'html': ['.html', '.htm'],
    'css': ['.css', '.scss', '.sass'],
    'json': ['.json'],
    'yaml': ['.yml', '.yaml'],
    'docker': ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml'],
    'makefile': ['Makefile'],
    'shell': ['.sh', '.bash'],
    'sql': ['.sql'],
    'markdown': ['.md']
}

# Категории кода
CATEGORIES = {
    'infrastructure': {
        'paths': ['infra/', 'docker-compose*.yml', 'Dockerfile*', 'Makefile'],
        'description': 'Инфраструктура и конфигурация'
    },
    'tests': {
        'paths': ['apps/*/tests/', 'tests/'],
        'description': 'Тесты'
    },
    'backend': {
        'paths': ['apps/api/', 'apps/backend/'],
        'description': 'Бэкенд API'
    },
    'frontend': {
        'paths': ['apps/frontend/', 'apps/web/'],
        'description': 'Фронтенд'
    },
    'models': {
        'paths': ['models/'],
        'description': 'Модели данных'
    },
    'docs': {
        'paths': ['docs/'],
        'description': 'Документация'
    },
    'scripts': {
        'paths': ['scripts/'],
        'description': 'Скрипты'
    }
}

# Исключения (файлы/папки которые не нужно включать)
EXCLUDE_PATTERNS = [
    '__pycache__',
    '.git',
    '.pytest_cache',
    'node_modules',
    '.venv',
    'venv',
    '.env',
    '*.pyc',
    '.DS_Store',
    '*.log',
    '*.tmp',
    '*.swp',
    '*.swo',
    '.coverage',
    'htmlcov',
    '.mypy_cache',
    '.tox',
    'dist',
    'build',
    '*.egg-info',
    '.idea',
    '.vscode',
    'generated'  # Исключаем папку generated
]

def should_exclude(file_path):
    """Проверяет, нужно ли исключить файл/папку"""
    path_str = str(file_path)
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_str:
            return True
    return False

def get_file_type(file_path):
    """Определяет тип файла по расширению"""
    suffix = file_path.suffix.lower()
    name = file_path.name.lower()
    
    for file_type, extensions in CODE_EXTENSIONS.items():
        if suffix in extensions or name in extensions:
            return file_type
    return 'other'

def collect_files(category_paths):
    """Собирает файлы для категории"""
    files = []
    
    for path_pattern in category_paths:
        if '*' in path_pattern:
            # Глобальный паттерн
            matches = glob.glob(str(PROJECT_ROOT / path_pattern), recursive=True)
            for match in matches:
                path = Path(match)
                if path.is_file() and not should_exclude(path):
                    files.append(path)
        else:
            # Обычный путь
            full_path = PROJECT_ROOT / path_pattern
            if full_path.exists():
                if full_path.is_file() and not should_exclude(full_path):
                    files.append(full_path)
                elif full_path.is_dir():
                    for file_path in full_path.rglob('*'):
                        if file_path.is_file() and not should_exclude(file_path):
                            files.append(file_path)
    
    # Убираем дубликаты и сортируем
    files = sorted(list(set(files)))
    return files

def read_file_content(file_path):
    """Читает содержимое файла с обработкой ошибок"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception:
            return f"[Ошибка чтения файла: {file_path}]"
    except Exception as e:
        return f"[Ошибка чтения файла {file_path}: {str(e)}]"

def generate_code_file():
    """Генерирует файл с полным кодом проекта"""
    print("🚀 Генерация полного кода проекта...")
    
    # Создаем директорию для вывода
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Удаляем старый файл если существует
    if OUTPUT_FILE.exists():
        print(f"🗑️  Удаляем старый файл: {OUTPUT_FILE}")
        OUTPUT_FILE.unlink()
    
    # Собираем статистику
    total_files = 0
    total_lines = 0
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        # Заголовок
        f.write("=" * 80 + "\n")
        f.write("ПОЛНЫЙ КОД ПРОЕКТА ML PORTAL\n")
        f.write("=" * 80 + "\n")
        f.write(f"Дата генерации: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Проект: {PROJECT_ROOT.name}\n")
        f.write("=" * 80 + "\n\n")
        
        # Генерируем каждую категорию
        for category_name, category_info in CATEGORIES.items():
            print(f"📁 Обрабатываем категорию: {category_info['description']}")
            
            files = collect_files(category_info['paths'])
            
            if not files:
                print(f"   ⚠️  Файлы не найдены для категории: {category_name}")
                continue
            
            # Заголовок категории
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"КАТЕГОРИЯ: {category_info['description'].upper()}\n")
            f.write("=" * 80 + "\n")
            f.write(f"Количество файлов: {len(files)}\n")
            f.write("=" * 80 + "\n\n")
            
            category_files = 0
            category_lines = 0
            
            # Обрабатываем файлы в категории
            for file_path in files:
                relative_path = file_path.relative_to(PROJECT_ROOT)
                file_type = get_file_type(file_path)
                
                print(f"   📄 {relative_path}")
                
                # Заголовок файла
                f.write(f"\n{'─' * 60}\n")
                f.write(f"ФАЙЛ: {relative_path}\n")
                f.write(f"ТИП: {file_type}\n")
                f.write(f"РАЗМЕР: {file_path.stat().st_size} байт\n")
                f.write(f"{'─' * 60}\n\n")
                
                # Содержимое файла
                content = read_file_content(file_path)
                f.write(content)
                
                if not content.endswith('\n'):
                    f.write('\n')
                
                # Статистика
                lines = content.count('\n')
                category_files += 1
                category_lines += lines
            
            # Статистика категории
            f.write(f"\n{'─' * 60}\n")
            f.write(f"СТАТИСТИКА КАТЕГОРИИ '{category_info['description']}':\n")
            f.write(f"Файлов: {category_files}\n")
            f.write(f"Строк: {category_lines}\n")
            f.write(f"{'─' * 60}\n")
            
            total_files += category_files
            total_lines += category_lines
        
        # Общая статистика
        f.write(f"\n{'=' * 80}\n")
        f.write("ОБЩАЯ СТАТИСТИКА ПРОЕКТА\n")
        f.write(f"{'=' * 80}\n")
        f.write(f"Всего файлов: {total_files}\n")
        f.write(f"Всего строк: {total_lines}\n")
        f.write(f"Размер файла: {OUTPUT_FILE.stat().st_size} байт\n")
        f.write(f"{'=' * 80}\n")
    
    print(f"\n✅ Генерация завершена!")
    print(f"📄 Файл создан: {OUTPUT_FILE}")
    print(f"📊 Статистика:")
    print(f"   - Файлов: {total_files}")
    print(f"   - Строк: {total_lines}")
    print(f"   - Размер: {OUTPUT_FILE.stat().st_size} байт")

def main():
    """Основная функция"""
    try:
        generate_code_file()
    except Exception as e:
        print(f"❌ Ошибка при генерации: {str(e)}")
        raise

if __name__ == "__main__":
    main()
