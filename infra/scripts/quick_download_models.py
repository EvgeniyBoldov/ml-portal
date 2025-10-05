#!/usr/bin/env python3
"""
Быстрое скачивание популярных моделей для ML Portal
"""
import os
import sys
from pathlib import Path

# Добавляем путь к скриптам
sys.path.append(str(Path(__file__).parent))

from download_models import download_model, get_model_info

def main():
    """Скачивает популярные модели для ML Portal"""
    
    # Определяем директорию для моделей
    models_dir = Path(__file__).parent.parent.parent / "models"
    models_dir.mkdir(exist_ok=True)
    
    # Популярные модели
    models = [
        {
            "id": "microsoft/DialoGPT-small",
            "type": "LLM",
            "description": "Small conversational model"
        },
        {
            "id": "microsoft/DialoGPT-medium", 
            "type": "LLM",
            "description": "Medium conversational model"
        },
        {
            "id": "sentence-transformers/all-MiniLM-L6-v2",
            "type": "Embeddings",
            "description": "Fast embeddings model"
        },
        {
            "id": "sentence-transformers/all-mpnet-base-v2",
            "type": "Embeddings", 
            "description": "High-quality embeddings model"
        }
    ]
    
    print("🚀 ML Portal - Quick Model Downloader")
    print("=" * 50)
    
    for model in models:
        print(f"\n📦 {model['type']}: {model['id']}")
        print(f"   {model['description']}")
        
        # Показываем информацию о модели
        info = get_model_info(model['id'])
        if info:
            print(f"   📥 Downloads: {info.get('downloads', 'N/A')}")
            print(f"   ❤️  Likes: {info.get('likes', 'N/A')}")
        
        # Скачиваем модель
        metadata = download_model(
            model_id=model['id'],
            output_dir=models_dir,
            include_patterns=["*.safetensors", "*.json", "*.txt", "*.py"],
            exclude_patterns=["*.bin", "*.h5", "*.onnx"]
        )
        
        if metadata:
            print(f"   ✅ Downloaded: {metadata['total_size_mb']:.1f} MB")
        else:
            print(f"   ❌ Failed to download")
    
    print(f"\n🎉 Download complete!")
    print(f"📁 Models saved in: {models_dir.absolute()}")

if __name__ == "__main__":
    main()
