#!/usr/bin/env python3
"""
Скрипт для скачивания конкретной модели из HuggingFace
"""
import subprocess
import sys
import argparse
from pathlib import Path

def run_command(cmd):
    """Выполняет команду и возвращает результат"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def main():
    """Скачивает указанную модель из HuggingFace"""
    
    parser = argparse.ArgumentParser(description="Скачивание конкретной модели из HuggingFace")
    parser.add_argument("model_id", help="ID модели для скачивания (например: BAAI/bge-3m)")
    parser.add_argument("--test", action="store_true", help="Тестировать скачанную модель")
    parser.add_argument("--info", action="store_true", help="Показать информацию о модели")
    parser.add_argument("--include", nargs="+", help="Включить только эти файлы (например: *.safetensors)")
    parser.add_argument("--exclude", nargs="+", help="Исключить эти файлы (например: *.bin)")
    parser.add_argument("--revision", "-r", help="Ревизия модели (по умолчанию: main)")
    
    args = parser.parse_args()
    
    print(f"🚀 Скачивание модели: {args.model_id}")
    print("=" * 50)
    
    # Показываем информацию о модели
    if args.info:
        print(f"📋 Получение информации о модели...")
        info_cmd = f"python3 scripts/download_models.py {args.model_id} --info"
        success, output = run_command(info_cmd)
        if success:
            print(output)
        else:
            print(f"⚠️  Не удалось получить информацию: {output}")
    
    print(f"\n💾 Модель будет сохранена в: {Path('models').absolute()}")
    
    # Спрашиваем подтверждение
    response = input(f"\n❓ Продолжить скачивание? (y/N): ").strip().lower()
    if response not in ['y', 'yes', 'да']:
        print("❌ Отменено пользователем")
        return
    
    print(f"\n📥 Начинаем скачивание...")
    
    # Формируем команду
    cmd_parts = [
        "python3 scripts/download_models.py",
        args.model_id
    ]
    
    # Добавляем опции
    if args.test:
        cmd_parts.append("--test")
    
    if args.include:
        cmd_parts.extend(["--include"] + args.include)
    else:
        # По умолчанию включаем только safetensors для экономии места
        cmd_parts.extend(["--include", "*.safetensors"])
    
    if args.exclude:
        cmd_parts.extend(["--exclude"] + args.exclude)
    else:
        # По умолчанию исключаем большие файлы
        cmd_parts.extend(["--exclude", "*.bin", "*.h5", "*.onnx"])
    
    if args.revision:
        cmd_parts.extend(["--revision", args.revision])
    
    cmd = " ".join(cmd_parts)
    print(f"🔧 Команда: {cmd}")
    print("-" * 40)
    
    # Выполняем команду
    success, output = run_command(cmd)
    
    if success:
        print(f"✅ Модель успешно скачана!")
        
        # Пытаемся извлечь размер из вывода
        for line in output.split('\n'):
            if 'Размер модели:' in line:
                try:
                    size_str = line.split('Размер модели:')[1].strip()
                    size_mb = float(size_str.replace(' MB', ''))
                    print(f"💾 Размер: {size_mb:.1f} MB")
                except:
                    pass
        
        print(f"\n🎉 Готово! Модель сохранена в директории models/")
        print(f"\n💡 Для использования:")
        print(f"   make list-models  # Показать скачанные модели")
        print(f"   make demo-embedding  # Тестировать систему эмбеддингов")
        
        # Показываем пример интеграции
        print(f"\n🔧 Для интеграции с системой эмбеддингов:")
        print(f"   1. Скопируйте модель в MinIO:")
        print(f"      aws s3 cp models/{args.model_id.replace('/', '--')}/ s3://models/{args.model_id}/default/ --recursive")
        print(f"   2. Обновите переменные в docker-compose:")
        print(f"      - EMB_MODEL_ID={args.model_id}")
        print(f"      - EMB_MODEL_ALIAS=your_alias")
        print(f"      - EMB_MODEL_REV=default")
        
    else:
        print(f"❌ Ошибка скачивания: {output}")
        print(f"\n💡 Возможные решения:")
        print(f"   - Проверьте правильность ID модели")
        print(f"   - Проверьте подключение к интернету")
        print(f"   - Установите зависимости: pip install huggingface_hub transformers torch")

if __name__ == "__main__":
    main()
