#!/usr/bin/env python3
"""
Скрипт для генерации txt файлов с описанием всего кода по направлениям
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Set
import re

class CodeDocumentationGenerator:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.output_dir = self.root_path
        
        # Определяем категории файлов
        self.categories = {
            'backend': {
                'extensions': ['.py'],
                'paths': ['apps/api', 'apps/emb', 'apps/llm'],
                'exclude_patterns': ['__pycache__', '.pyc', 'migrations', 'node_modules', '.git', 'tests']
            },
            'tests': {
                'extensions': ['.py'],
                'paths': ['apps/api/src/app/tests'],
                'exclude_patterns': ['__pycache__', '.pyc', 'node_modules', '.git']
            },
            'frontend': {
                'extensions': ['.ts', '.tsx', '.js', '.jsx', '.css', '.html', '.json'],
                'paths': ['apps/web'],
                'exclude_patterns': ['node_modules', '.git', 'dist', 'build', 'coverage']
            },
            'infrastructure': {
                'extensions': ['.yml', '.yaml', '.dockerfile', '.sh', '.conf', '.ini', '.toml', '.txt'],
                'paths': ['infra', 'docker-compose.yml', 'docker-compose.dev.yml', 'docker-compose.prod.yml', 'docker-compose.test.yml', 'Makefile', 'env.example'],
                'exclude_patterns': ['node_modules', '.git', '__pycache__']
            }
        }
    
    def should_exclude_file(self, file_path: Path, exclude_patterns: List[str]) -> bool:
        """Проверяет, нужно ли исключить файл"""
        path_str = str(file_path)
        for pattern in exclude_patterns:
            if pattern in path_str:
                return True
        return False
    
    def get_file_content(self, file_path: Path) -> str:
        """Получает содержимое файла"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Ограничиваем размер для больших файлов
            if len(content) > 10000:  # Если файл больше 10KB
                lines = content.split('\n')
                if len(lines) > 200:  # Если больше 200 строк
                    content = '\n'.join(lines[:200]) + '\n... (файл обрезан, показаны первые 200 строк)'
            
            return content
            
        except Exception as e:
            return f"Ошибка чтения файла: {str(e)}"
    
    def collect_files(self, category: str) -> Dict[str, List[Dict]]:
        """Собирает файлы для указанной категории"""
        category_config = self.categories[category]
        files_by_path = {}
        
        for path_config in category_config['paths']:
            if path_config.startswith('apps/'):
                # Это директория в apps
                full_path = self.root_path / path_config
                if full_path.exists():
                    files_by_path[path_config] = self._scan_directory(full_path, category_config)
            else:
                # Это конкретный файл
                file_path = self.root_path / path_config
                if file_path.exists():
                    if file_path.is_file():
                        files_by_path[path_config] = [{
                            'name': file_path.name,
                            'path': str(file_path.relative_to(self.root_path)),
                            'size': file_path.stat().st_size,
                            'content': self.get_file_content(file_path)
                        }]
                    else:
                        files_by_path[path_config] = self._scan_directory(file_path, category_config)
        
        return files_by_path
    
    def _scan_directory(self, directory: Path, category_config: Dict) -> List[Dict]:
        """Сканирует директорию и возвращает список файлов"""
        files = []
        
        try:
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    # Проверяем расширение файла
                    if file_path.suffix.lower() in category_config['extensions']:
                        # Проверяем исключения
                        if not self.should_exclude_file(file_path, category_config['exclude_patterns']):
                            files.append({
                                'name': file_path.name,
                                'path': str(file_path.relative_to(self.root_path)),
                                'size': file_path.stat().st_size,
                                'content': self.get_file_content(file_path)
                            })
        except Exception as e:
            print(f"Ошибка при сканировании {directory}: {e}")
        
        return sorted(files, key=lambda x: x['path'])
    
    def generate_documentation(self):
        """Генерирует документацию для всех категорий"""
        print("🚀 Генерация документации кода...")
        
        for category in self.categories.keys():
            print(f"📁 Обработка категории: {category}")
            
            files_by_path = self.collect_files(category)
            
            # Создаем содержимое файла
            content = []
            content.append(f"# Документация кода - {category.upper()}")
            content.append(f"# Сгенерировано: {Path().cwd()}")
            content.append(f"# Корень проекта: {self.root_path}")
            content.append("")
            content.append("=" * 80)
            content.append("")
            
            total_files = 0
            total_size = 0
            
            for path_name, files in files_by_path.items():
                if not files:
                    continue
                    
                content.append(f"## 📂 {path_name}")
                content.append("")
                
                for file_info in files:
                    total_files += 1
                    total_size += file_info['size']
                    
                    size_kb = file_info['size'] / 1024
                    content.append(f"### 📄 {file_info['name']}")
                    content.append(f"**Путь:** `{file_info['path']}`")
                    content.append(f"**Размер:** {size_kb:.1f} KB")
                    content.append("")
                    content.append("```")
                    content.append(file_info['content'])
                    content.append("```")
                    content.append("")
                    content.append("---")
                    content.append("")
            
            content.append("=" * 80)
            content.append(f"**Итого файлов:** {total_files}")
            content.append(f"**Общий размер:** {total_size / 1024 / 1024:.1f} MB")
            content.append("")
            
            # Сохраняем файл
            output_file = self.output_dir / f"code-docs-{category}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content))
            
            print(f"✅ Создан файл: {output_file}")
        
        print("🎉 Генерация завершена!")

def main():
    if len(sys.argv) > 1:
        root_path = sys.argv[1]
    else:
        root_path = os.getcwd()
    
    generator = CodeDocumentationGenerator(root_path)
    generator.generate_documentation()

if __name__ == "__main__":
    main()
