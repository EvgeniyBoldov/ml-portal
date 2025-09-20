#!/usr/bin/env python3
"""
Скрипт для генерации структуры проекта.
Создает project-structure.txt с древовидной структурой файлов.
"""

import os
import sys
from pathlib import Path
from typing import List, Set

# Файлы и директории для исключения
EXCLUDE_PATTERNS = {
    'node_modules', '__pycache__', '.git', '.venv', '.env',
    'dist', 'build', '.pytest_cache', '.cache', '.vscode',
    '.idea', '.DS_Store', '*.pyc', '*.pyo', '*.pyd',
    '*.tsbuildinfo', '*.log', '*.tmp', '*.temp', 'migrations',
    'coverage', 'test-results', 'playwright-report', '.terraform',
    'terraform.tfstate*', '.terraform.lock.hcl', '.next',
    'target', 'Cargo.lock', '*.egg-info', '.mypy_cache',
    '.coverage', 'htmlcov', '.nyc_output', '.nyc_output',
    'node_modules', 'bower_components', '.sass-cache',
    '.parcel-cache', '.turbo', '.next', 'out', 'public',
    'static', 'assets', 'vendor', 'lib-cov', 'coverage',
    '.nyc_output', '.grunt', 'bower_components', '.lock-wscript',
    'build/Release', 'node_modules', 'jspm_packages', 'typings',
    '.npm', '.eslintcache', '.stylelintcache', '.rpt2_cache',
    '.rts2_cache_cjs', '.rts2_cache_es', '.rts2_cache_umd',
    '.caches', '.yarn-integrity', '.env.local', '.env.development.local',
    '.env.test.local', '.env.production.local', 'npm-debug.log*',
    'yarn-debug.log*', 'yarn-error.log*', 'lerna-debug.log*',
    '.pnpm-debug.log*', 'report.[0-9]*.[0-9]*.[0-9]*.[0-9]*.json',
    'pids', '*.pid', '*.seed', '*.pid.lock', 'lib-cov',
    'coverage', '.nyc_output', '.grunt', 'bower_components',
    '.lock-wscript', 'build/Release', 'node_modules', 'jspm_packages',
    'typings', '.npm', '.eslintcache', '.stylelintcache',
    '.rpt2_cache', '.rts2_cache_cjs', '.rts2_cache_es',
    '.rts2_cache_umd', '.caches', '.yarn-integrity'
}

# Файлы для исключения по имени
EXCLUDE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    '*.min.js', '*.min.css', '*.bundle.js', 'alembic.ini',
    'terraform.tfstate', 'terraform.tfstate.backup',
    '*.pyc', '*.pyo', '*.pyd', '*.so', '*.dylib', '*.dll',
    '*.exe', '*.bin', '*.o', '*.a', '*.lib', '*.dll.a',
    '*.so.*', '*.dylib.*', '*.dll.*', '*.exe.*', '*.bin.*',
    '*.o.*', '*.a.*', '*.lib.*', '*.dll.a.*', '*.so.*.*',
    '*.dylib.*.*', '*.dll.*.*', '*.exe.*.*', '*.bin.*.*',
    '*.o.*.*', '*.a.*.*', '*.lib.*.*', '*.dll.a.*.*'
}

def should_include_item(item_path: Path) -> bool:
    """Проверяет, нужно ли включать файл/директорию в структуру."""
    
    # Проверяем исключаемые паттерны в пути
    path_str = str(item_path).lower()
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_str:
            return False
    
    # Проверяем исключаемые файлы
    for pattern in EXCLUDE_FILES:
        if item_path.name == pattern or item_path.name.endswith(pattern.replace('*', '')):
            return False
    
    return True

def get_file_size(file_path: Path) -> str:
    """Возвращает размер файла в удобочитаемом формате."""
    try:
        size = file_path.stat().st_size
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f}GB"
    except:
        return "?"

def generate_structure_tree(
    directory: Path, 
    project_root: Path, 
    output_lines: List[str], 
    prefix: str = "",
    is_last: bool = True,
    max_depth: int = 10,
    current_depth: int = 0
) -> None:
    """Рекурсивно генерирует древовидную структуру проекта."""
    
    if not directory.exists() or not directory.is_dir():
        return
    
    if current_depth >= max_depth:
        output_lines.append(f"{prefix}{'└── ' if is_last else '├── '}[... (max depth reached)]")
        return
    
    # Получаем все элементы, отсортированные по типу (директории сначала) и имени
    items = []
    for item in directory.iterdir():
        if should_include_item(item):
            items.append(item)
    
    # Сортируем: директории сначала, затем файлы, все по алфавиту
    items.sort(key=lambda x: (x.is_file(), x.name.lower()))
    
    for i, item in enumerate(items):
        is_last_item = i == len(items) - 1
        current_prefix = "└── " if is_last_item else "├── "
        
        if item.is_file():
            # Файл
            size = get_file_size(item)
            output_lines.append(f"{prefix}{current_prefix}{item.name} ({size})")
        else:
            # Директория
            output_lines.append(f"{prefix}{current_prefix}{item.name}/")
            
            # Рекурсивно обрабатываем поддиректорию
            next_prefix = prefix + ("    " if is_last_item else "│   ")
            generate_structure_tree(
                item, 
                project_root, 
                output_lines, 
                next_prefix, 
                is_last_item,
                max_depth,
                current_depth + 1
            )

def generate_flat_structure(
    directory: Path, 
    project_root: Path, 
    output_lines: List[str]
) -> None:
    """Генерирует плоский список всех файлов проекта."""
    
    def collect_files(dir_path: Path):
        if not dir_path.exists() or not dir_path.is_dir():
            return
        
        for item in dir_path.iterdir():
            if item.is_file() and should_include_item(item):
                # Вычисляем относительный путь от корня проекта
                try:
                    rel_path = item.relative_to(project_root)
                    path_str = str(rel_path).replace('\\', '/')
                    size = get_file_size(item)
                    output_lines.append(f"{path_str} ({size})")
                except ValueError:
                    # Файл не находится внутри project_root
                    pass
            elif item.is_dir() and should_include_item(item):
                collect_files(item)
    
    collect_files(directory)

def generate_project_structure(project_root: Path) -> str:
    """Генерирует структуру проекта."""
    output_lines = []
    
    output_lines.append("ML Portal - Project Structure")
    output_lines.append("=" * 50)
    output_lines.append(f"Generated from: {project_root}")
    output_lines.append(f"Generated at: {Path(__file__).stat().st_mtime}")
    output_lines.append("")
    
    # Древовидная структура
    output_lines.append("TREE STRUCTURE:")
    output_lines.append("=" * 30)
    output_lines.append("ml-portal/")
    generate_structure_tree(project_root, project_root, output_lines, "", True)
    
    output_lines.append("")
    output_lines.append("")
    output_lines.append("FLAT FILE LIST:")
    output_lines.append("=" * 30)
    
    # Плоский список файлов
    flat_files = []
    generate_flat_structure(project_root, project_root, flat_files)
    flat_files.sort()
    
    for file_path in flat_files:
        output_lines.append(file_path)
    
    output_lines.append("")
    output_lines.append(f"Total files: {len(flat_files)}")
    
    return "\n".join(output_lines)

def main():
    """Основная функция."""
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path(__file__).parent.parent.parent.resolve()
    
    print(f"Generating project structure from: {project_root}")
    
    # Создаем директорию для выходных файлов
    output_dir = project_root / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем структуру проекта
    print("Generating project structure...")
    structure = generate_project_structure(project_root)
    structure_file = output_dir / "project-structure.txt"
    with open(structure_file, 'w', encoding='utf-8') as f:
        f.write(structure)
    print(f"Project structure written to: {structure_file}")
    
    print("Project structure generation complete!")

if __name__ == "__main__":
    main()
