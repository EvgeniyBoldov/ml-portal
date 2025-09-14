#!/usr/bin/env python3
"""
Простое скачивание моделей без тестирования (для легких моделей)
"""
import os
import sys
import argparse
from pathlib import Path
from huggingface_hub import snapshot_download

def download_model_simple(model_id: str, output_dir: str = "models") -> bool:
    """Простое скачивание модели без тестирования"""
    try:
        print(f"📥 Скачивание модели: {model_id}")
        
        # Создаем директорию
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Скачиваем модель
        model_dir = output_path / model_id.replace("/", "--")
        model_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"💾 Сохранение в: {model_dir}")
        
        # Скачиваем только основные файлы
        downloaded_path = snapshot_download(
            repo_id=model_id,
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
            ignore_patterns=["*.bin", "*.h5", "*.onnx", "*.ckpt", "*.pth"]  # Исключаем большие файлы
        )
        
        print(f"✅ Модель скачана: {downloaded_path}")
        
        # Показываем размер
        total_size = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
        print(f"📊 Размер: {total_size / (1024*1024):.1f} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Простое скачивание моделей")
    parser.add_argument("model_id", help="ID модели")
    parser.add_argument("--output-dir", default="models", help="Директория для сохранения")
    
    args = parser.parse_args()
    
    success = download_model_simple(args.model_id, args.output_dir)
    
    if success:
        print(f"\n🎉 Готово! Модель сохранена в {args.output_dir}/")
        print(f"💡 Для использования в docker-compose:")
        print(f"   - EMB_MODEL_ID={args.model_id}")
        print(f"   - EMB_MODEL_ALIAS={args.model_id.split('/')[-1]}")
    else:
        print(f"\n❌ Не удалось скачать модель")
        sys.exit(1)

if __name__ == "__main__":
    main()
