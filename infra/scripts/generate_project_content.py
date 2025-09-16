#!/usr/bin/env python3
"""
Скрипт для генерации полного содержимого проекта в текстовые файлы.
Создает apps.txt и infra.txt с содержимым всех файлов проекта.
"""

import os
import sys
from pathlib import Path
from typing import List, Set

# Расширения файлов для включения
INCLUDE_EXTENSIONS = {
    # Код
    '.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.yaml', '.yml',
    # Конфигурация
    '.toml', '.ini', '.cfg', '.conf', '.config',
    # Стили и разметка
    '.css', '.scss', '.sass', '.html', '.md', '.txt',
    # Docker и инфраструктура
    '.dockerfile', '.Dockerfile', '.sh', '.bash',
    # Другие
    '.sql', '.env', '.gitignore', '.editorconfig'
}

# Файлы и директории для исключения
EXCLUDE_PATTERNS = {
    'node_modules', '__pycache__', '.git', '.venv', '.env',
    'dist', 'build', '.pytest_cache', '.cache', '.vscode',
    '.idea', '.DS_Store', '*.pyc', '*.pyo', '*.pyd',
    '*.tsbuildinfo', '*.log', '*.tmp', '*.temp'
}

# Файлы для исключения по имени
EXCLUDE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    '*.min.js', '*.min.css', '*.bundle.js'
}

def should_include_file(file_path: Path) -> bool:
    """Проверяет, нужно ли включать файл в генерацию."""
    
    # Проверяем расширение
    if file_path.suffix.lower() not in INCLUDE_EXTENSIONS:
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

def generate_content_for_directory(directory: Path, project_root: Path, output_lines: List[str]):
    """Рекурсивно генерирует содержимое для директории."""
    
    if not directory.exists() or not directory.is_dir():
        return
    
    # Получаем все файлы и директории, отсортированные по имени
    items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    
    for item in items:
        if item.is_file() and should_include_file(item):
            # Вычисляем относительный путь от корня проекта
            relative_path = item.relative_to(project_root)
            path_str = str(relative_path).replace('\\', '/')  # Нормализуем пути
            
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
            generate_content_for_directory(item, project_root, output_lines)

def generate_apps_content(project_root: Path) -> str:
    """Генерирует содержимое для apps/ директории."""
    output_lines = []
    
    output_lines.append("ML Portal - Apps Content")
    output_lines.append("=" * 50)
    output_lines.append(f"Generated from: {project_root}")
    output_lines.append(f"Directory: apps/")
    output_lines.append("")
    
    apps_dir = project_root / "apps"
    if apps_dir.exists():
        generate_content_for_directory(apps_dir, project_root, output_lines)
    else:
        output_lines.append("# apps/ directory not found")
    
    return "\n".join(output_lines)

def generate_infra_content(project_root: Path) -> str:
    """Генерирует содержимое для infra/ директории."""
    output_lines = []
    
    output_lines.append("ML Portal - Infrastructure Content")
    output_lines.append("=" * 50)
    output_lines.append(f"Generated from: {project_root}")
    output_lines.append(f"Directory: infra/")
    output_lines.append("")
    
    infra_dir = project_root / "infra"
    if infra_dir.exists():
        generate_content_for_directory(infra_dir, project_root, output_lines)
    else:
        output_lines.append("# infra/ directory not found")
    
    return "\n".join(output_lines)

def main():
    """Основная функция."""
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path(__file__).parent.parent.parent.resolve()
    
    print(f"Generating project content from: {project_root}")
    
    # Создаем директорию для выходных файлов
    output_dir = project_root / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем содержимое для apps
    print("Generating apps content...")
    apps_content = generate_apps_content(project_root)
    apps_file = output_dir / "apps.txt"
    with open(apps_file, 'w', encoding='utf-8') as f:
        f.write(apps_content)
    print(f"Apps content written to: {apps_file}")
    
    # Генерируем содержимое для infra
    print("Generating infra content...")
    infra_content = generate_infra_content(project_root)
    infra_file = output_dir / "infra.txt"
    with open(infra_file, 'w', encoding='utf-8') as f:
        f.write(infra_content)
    print(f"Infra content written to: {infra_file}")
    
    print("Generation complete!")

if __name__ == "__main__":
    main()
