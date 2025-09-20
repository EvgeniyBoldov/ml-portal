#!/usr/bin/env python3
"""
Скрипт для генерации кода инфраструктуры.
Создает infra-code.txt с полными путями от корня проекта.
"""

import os
import sys
from pathlib import Path
from typing import List, Set

# Расширения файлов для инфраструктуры
INFRA_EXTENSIONS = {
    '.py', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.config', 
    '.sh', '.bash', '.dockerfile', '.env', '.env.example', '.gitignore',
    '.dockerignore', '.gitattributes', '.json', '.md', '.txt', '.sql',
    '.hcl', '.tf', '.tfvars', '.tfstate', '.tfstate.backup'
}

# Файлы и директории для исключения
EXCLUDE_PATTERNS = {
    'node_modules', '__pycache__', '.git', '.venv', '.env',
    'dist', 'build', '.pytest_cache', '.cache', '.vscode',
    '.idea', '.DS_Store', '*.pyc', '*.pyo', '*.pyd',
    '*.tsbuildinfo', '*.log', '*.tmp', '*.temp', 'migrations',
    'coverage', 'test-results', 'playwright-report', '.terraform',
    'terraform.tfstate*', '.terraform.lock.hcl'
}

# Файлы для исключения по имени
EXCLUDE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    '*.min.js', '*.min.css', '*.bundle.js', 'alembic.ini',
    'terraform.tfstate', 'terraform.tfstate.backup'
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

def generate_infra_for_directory(
    directory: Path, 
    project_root: Path, 
    output_lines: List[str], 
    extensions: Set[str],
    component_type: str
) -> None:
    """Рекурсивно генерирует код инфраструктуры для директории."""
    
    if not directory.exists() or not directory.is_dir():
        return
    
    # Получаем все файлы и директории, отсортированные по имени
    items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    
    for item in items:
        if item.is_file() and should_include_file(item, extensions):
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
            generate_infra_for_directory(item, project_root, output_lines, extensions, component_type)

def generate_infra_code(project_root: Path) -> str:
    """Генерирует код инфраструктуры."""
    output_lines = []
    
    output_lines.append("ML Portal - Infrastructure Code")
    output_lines.append("=" * 50)
    output_lines.append(f"Generated from: {project_root}")
    output_lines.append(f"Component: Infrastructure (infra/)")
    output_lines.append("")
    
    # Обрабатываем основную директорию инфраструктуры
    infra_dir = project_root / "infra"
    if infra_dir.exists():
        generate_infra_for_directory(infra_dir, project_root, output_lines, INFRA_EXTENSIONS, "infrastructure")
    else:
        output_lines.append("# infra/ directory not found")
    
    # Обрабатываем корневые файлы инфраструктуры
    root_infra_files = [
        "docker-compose.yml", "docker-compose.yaml", "Dockerfile", 
        "Makefile", "README.md", ".gitignore", ".env.example",
        "requirements.txt", "pyproject.toml", "setup.py"
    ]
    
    for file_name in root_infra_files:
        file_path = project_root / file_name
        if file_path.exists() and should_include_file(file_path, INFRA_EXTENSIONS):
            full_path = file_path.relative_to(project_root)
            path_str = str(full_path).replace('\\', '/')
            
            output_lines.append(f"\n{'#' * 80}")
            output_lines.append(f"# {path_str}")
            output_lines.append(f"{'#' * 80}")
            
            content = read_file_content(file_path, project_root)
            if content.strip():
                output_lines.append(content)
            else:
                output_lines.append("# (empty file)")
    
    return "\n".join(output_lines)

def main():
    """Основная функция."""
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path(__file__).parent.parent.parent.resolve()
    
    print(f"Generating infrastructure code from: {project_root}")
    
    # Создаем директорию для выходных файлов
    output_dir = project_root / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем код инфраструктуры
    print("Generating infrastructure code...")
    infra_code = generate_infra_code(project_root)
    infra_file = output_dir / "infra-code.txt"
    with open(infra_file, 'w', encoding='utf-8') as f:
        f.write(infra_code)
    print(f"Infrastructure code written to: {infra_file}")
    
    print("Infrastructure code generation complete!")

if __name__ == "__main__":
    main()
