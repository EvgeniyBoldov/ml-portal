#!/usr/bin/env python3
"""
Скрипт для скачивания моделей из HuggingFace в локальную директорию
"""
import os
import sys
import argparse
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from huggingface_hub import snapshot_download, hf_hub_download
    from transformers import AutoTokenizer, AutoModel
    import torch
except ImportError:
    print("❌ Необходимо установить зависимости:")
    print("pip install huggingface_hub transformers torch")
    sys.exit(1)

def calculate_checksum(file_path: Path) -> str:
    """Вычисляет SHA256 checksum файла"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return f"sha256:{sha256_hash.hexdigest()}"

def download_model(
    model_id: str, 
    output_dir: Path, 
    revision: Optional[str] = None,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Скачивает модель из HuggingFace"""
    
    print(f"📥 Скачивание модели: {model_id}")
    if revision:
        print(f"   Ревизия: {revision}")
    
    # Создаем директорию для модели
    model_dir = output_dir / model_id.replace("/", "--")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Скачиваем модель
        downloaded_path = snapshot_download(
            repo_id=model_id,
            revision=revision,
            local_dir=str(model_dir),
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            local_dir_use_symlinks=False  # Копируем файлы, а не создаем симлинки
        )
        
        print(f"✅ Модель скачана в: {model_dir}")
        
        # Вычисляем checksums для всех файлов
        checksums = {}
        for file_path in model_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(model_dir)
                checksum = calculate_checksum(file_path)
                checksums[str(relative_path)] = checksum
                print(f"   📄 {relative_path}: {checksum[:16]}...")
        
        # Создаем метаданные модели
        metadata = {
            "model_id": model_id,
            "revision": revision or "main",
            "downloaded_at": str(Path().cwd()),
            "files": checksums,
            "total_files": len(checksums),
            "total_size_mb": sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        }
        
        # Сохраняем метаданные
        metadata_file = model_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"📊 Размер модели: {metadata['total_size_mb']:.1f} MB")
        print(f"📄 Файлов: {metadata['total_files']}")
        
        return metadata
        
    except Exception as e:
        print(f"❌ Ошибка скачивания модели {model_id}: {e}")
        return {}

def get_model_info(model_id: str, revision: Optional[str] = None) -> Dict[str, Any]:
    """Получает информацию о модели"""
    try:
        from huggingface_hub import model_info
        info = model_info(model_id, revision=revision)
        
        return {
            "id": info.id,
            "pipeline_tag": getattr(info, 'pipeline_tag', None),
            "tags": getattr(info, 'tags', []),
            "downloads": getattr(info, 'downloads', 0),
            "likes": getattr(info, 'likes', 0),
            "created_at": getattr(info, 'created_at', None),
            "last_modified": getattr(info, 'last_modified', None),
        }
    except Exception as e:
        print(f"⚠️  Не удалось получить информацию о модели: {e}")
        return {}

def test_model(model_id: str, model_dir: Path) -> bool:
    """Тестирует загруженную модель"""
    try:
        print(f"🧪 Тестирование модели: {model_id}")
        
        # Пробуем загрузить токенайзер
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        print(f"   ✅ Токенайзер загружен")
        
        # Пробуем загрузить модель
        model = AutoModel.from_pretrained(str(model_dir))
        print(f"   ✅ Модель загружена")
        
        # Простой тест
        test_text = "Hello, world!"
        inputs = tokenizer(test_text, return_tensors="pt")
        
        with torch.no_grad():
            outputs = model(**inputs)
        
        print(f"   ✅ Тест прошел успешно")
        print(f"   📊 Размерность выхода: {outputs.last_hidden_state.shape}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка тестирования: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Скачивание моделей из HuggingFace")
    parser.add_argument("models", nargs="+", help="ID моделей для скачивания")
    parser.add_argument("--output-dir", "-o", default="models", help="Директория для сохранения (по умолчанию: models)")
    parser.add_argument("--revision", "-r", help="Ревизия модели (по умолчанию: main)")
    parser.add_argument("--include", nargs="+", help="Включить только эти файлы (например: *.safetensors)")
    parser.add_argument("--exclude", nargs="+", help="Исключить эти файлы (например: *.bin)")
    parser.add_argument("--test", action="store_true", help="Тестировать скачанные модели")
    parser.add_argument("--info", action="store_true", help="Показать информацию о моделях")
    
    args = parser.parse_args()
    
    # Создаем директорию для моделей
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    print(f"🚀 Скачивание моделей в: {output_dir.absolute()}")
    print("=" * 60)
    
    results = []
    
    for model_id in args.models:
        print(f"\n📦 Обработка модели: {model_id}")
        print("-" * 40)
        
        # Показываем информацию о модели
        if args.info:
            info = get_model_info(model_id, args.revision)
            if info:
                print(f"   📋 ID: {info.get('id', 'N/A')}")
                print(f"   🏷️  Pipeline: {info.get('pipeline_tag', 'N/A')}")
                print(f"   📥 Downloads: {info.get('downloads', 'N/A')}")
                print(f"   ❤️  Likes: {info.get('likes', 'N/A')}")
        
        # Скачиваем модель
        metadata = download_model(
            model_id=model_id,
            output_dir=output_dir,
            revision=args.revision,
            include_patterns=args.include,
            exclude_patterns=args.exclude
        )
        
        if metadata:
            results.append(metadata)
            
            # Тестируем модель
            if args.test:
                model_dir = output_dir / model_id.replace("/", "--")
                test_model(model_id, model_dir)
        else:
            print(f"❌ Не удалось скачать модель: {model_id}")
    
    # Создаем сводный отчет
    if results:
        print(f"\n📊 Сводный отчет")
        print("=" * 60)
        
        total_size = sum(r.get('total_size_mb', 0) for r in results)
        total_files = sum(r.get('total_files', 0) for r in results)
        
        print(f"✅ Успешно скачано моделей: {len(results)}")
        print(f"📄 Общее количество файлов: {total_files}")
        print(f"💾 Общий размер: {total_size:.1f} MB")
        
        # Сохраняем сводный отчет
        report_file = output_dir / "download_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({
                "downloaded_at": str(Path().cwd()),
                "total_models": len(results),
                "total_files": total_files,
                "total_size_mb": total_size,
                "models": results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Отчет сохранен в: {report_file}")
        
        # Показываем структуру директорий
        print(f"\n📁 Структура директорий:")
        for model_dir in output_dir.iterdir():
            if model_dir.is_dir():
                print(f"   📂 {model_dir.name}")
                for file in sorted(model_dir.iterdir()):
                    if file.is_file():
                        size_mb = file.stat().st_size / (1024 * 1024)
                        print(f"      📄 {file.name} ({size_mb:.1f} MB)")
    
    print(f"\n🎉 Готово!")

if __name__ == "__main__":
    main()
