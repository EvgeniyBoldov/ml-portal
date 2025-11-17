#!/usr/bin/env python3
"""
Скрипт для скачивания моделей из HuggingFace в локальную директорию
"""
import sys
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_DIR = REPO_ROOT / "models_llm"
DEFAULT_MODELS_FILE = REPO_ROOT / "models.txt"

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("❌ Необходимо установить huggingface_hub")
    print("pip install huggingface_hub")
    sys.exit(1)

def calculate_checksum(file_path: Path) -> str:
    """Вычисляет SHA256 checksum файла"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return f"sha256:{sha256_hash.hexdigest()}"


def load_models_from_file(file_path: Path) -> List[str]:
    """Загружает список моделей из файла"""
    if not file_path.exists():
        print(f"❌ Файл со списком моделей не найден: {file_path}")
        return []

    models: List[str] = []
    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            models.append(line)

    if not models:
        print(f"⚠️ Файл {file_path} не содержит моделей для скачивания")

    return models


def model_already_downloaded(model_id: str, output_dir: Path) -> bool:
    """Проверяет, загружена ли модель ранее"""
    model_dir = output_dir / model_id.replace("/", "--")
    if not model_dir.exists():
        return False

    for item in model_dir.rglob("*"):
        if item.is_file():
            return True

    return False


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
        download_kwargs: Dict[str, Any] = {
            "repo_id": model_id,
            "local_dir": str(model_dir),
        }

        if revision:
            download_kwargs["revision"] = revision
        if include_patterns:
            download_kwargs["allow_patterns"] = include_patterns
        if exclude_patterns:
            download_kwargs["ignore_patterns"] = exclude_patterns

        snapshot_download(**download_kwargs)
        
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
            "downloaded_at": datetime.utcnow().isoformat(),
            "files": checksums,
            "total_files": len(checksums),
            "total_size_mb": sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        }
        
        # Сохраняем метаданные
        metadata_file = model_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Пишем manifest.json для сканера реестра моделей
        # Короткое имя модели (alias) — последняя часть после '/'
        alias = model_id.split("/")[-1]
        # Простая эвристика модальности: считаем эти модели эмбеддингами текста
        modality = "text"
        # Карта известных размерностей
        vector_dim_map = {
            "all-MiniLM-L6-v2": 384,
            "multilingual-e5-small": 384,
            "bge-large-en": 1024,
        }
        vector_dim = vector_dim_map.get(alias, 384)

        manifest = {
            "model": alias,
            "version": "latest",
            "modality": modality,
            "vector_dim": vector_dim,
        }
        manifest_file = model_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"🧾 manifest.json создан для {alias} → {manifest_file}")

        print(f"📊 Размер модели: {metadata['total_size_mb']:.1f} MB")
        print(f"📄 Файлов: {metadata['total_files']}")
        
        return metadata

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

def main():
    parser = argparse.ArgumentParser(description="Скачивание моделей из HuggingFace")
    parser.add_argument(
        "models",
        nargs="*",
        help="ID моделей для скачивания. Если список пуст — используется файл (--models-file)"
    )
    parser.add_argument(
        "--models-file",
        default=str(DEFAULT_MODELS_FILE),
        help="Путь к файлу со списком моделей (по умолчанию: ./models.txt)"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=str(DEFAULT_MODELS_DIR),
        help="Директория для сохранения (по умолчанию: ./models_llm)"
    )
    parser.add_argument("--revision", "-r", help="Ревизия модели (по умолчанию: main)")
    parser.add_argument("--include", nargs="+", help="Включить только эти файлы (например: *.safetensors)")
    parser.add_argument("--exclude", nargs="+", help="Исключить эти файлы (например: *.bin)")
    parser.add_argument("--info", action="store_true", help="Показать информацию о моделях")
    parser.add_argument("--force", action="store_true", help="Перекачать модели даже если они уже существуют")

    args = parser.parse_args()

    # Определяем список моделей
    models: List[str] = args.models
    if not models:
        models = load_models_from_file(Path(args.models_file))

    if not models:
        print("❌ Не найдено моделей для скачивания. Укажите их аргументом или в файле.")
        sys.exit(1)

    # Создаем директорию для моделей
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Скачивание моделей в: {output_dir.absolute()}")
    print("=" * 60)

    results = []
    skipped: List[str] = []

    for model_id in models:
        print(f"\n📦 Обработка модели: {model_id}")
        print("-" * 40)

        if model_already_downloaded(model_id, output_dir) and not args.force:
            print(f"⚡ Модель уже скачана, пропускаю")
            skipped.append(model_id)
            continue

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
                "downloaded_at": datetime.utcnow().isoformat(),
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
    
    if skipped:
        print("\nℹ️ Пропущены уже загруженные модели:")
        for model in skipped:
            print(f"   • {model}")

    print(f"\n🎉 Готово!")

if __name__ == "__main__":
    main()
