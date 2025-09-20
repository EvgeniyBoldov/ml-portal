#!/usr/bin/env python3
"""
Скрипт для исправления импортов в проекте
"""
import os
import re
from pathlib import Path

def fix_imports_in_file(file_path):
    """Исправляет импорты в одном файле"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Паттерны для замены
    patterns = [
        # from app. -> from apps.api.src.app.
        (r'from app\.', 'from apps.api.src.app.'),
        # import app. -> import apps.api.src.app.
        (r'import app\.', 'import apps.api.src.app.'),
    ]
    
    original_content = content
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed imports in: {file_path}")
        return True
    return False

def main():
    """Основная функция"""
    project_root = Path(__file__).parent
    api_dir = project_root / "apps" / "api" / "src" / "app"
    
    if not api_dir.exists():
        print(f"Directory not found: {api_dir}")
        return
    
    fixed_files = 0
    for py_file in api_dir.rglob("*.py"):
        if fix_imports_in_file(py_file):
            fixed_files += 1
    
    print(f"Fixed imports in {fixed_files} files")

if __name__ == "__main__":
    main()

