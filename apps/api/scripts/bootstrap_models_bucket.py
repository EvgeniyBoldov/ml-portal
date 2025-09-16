#!/usr/bin/env python3
"""
Скрипт для создания бакета моделей в MinIO
"""
import os
import boto3
from botocore.exceptions import ClientError

def create_models_bucket():
    """Создает бакет для моделей в MinIO"""
    
    # Настройки MinIO
    endpoint_url = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
    bucket_name = os.getenv("MODELS_BUCKET", "models")
    
    try:
        # Создаем S3 клиент
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        
        # Проверяем, существует ли бакет
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"Bucket '{bucket_name}' already exists")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # Бакет не существует, создаем
                pass
            else:
                raise
        
        # Создаем бакет
        s3_client.create_bucket(Bucket=bucket_name)
        print(f"Created bucket '{bucket_name}'")
        
        # Создаем тестовую структуру
        test_structure = [
            "sentence-transformers/all-MiniLM-L6-v2/default/config.json",
            "sentence-transformers/all-MiniLM-L6-v2/default/pytorch_model.bin",
            "sentence-transformers/all-MiniLM-L6-v2/default/tokenizer.json",
            "sentence-transformers/all-MiniLM-L6-v2/default/tokenizer_config.json",
            "sentence-transformers/all-MiniLM-L6-v2/default/vocab.txt",
        ]
        
        for key in test_structure:
            # Создаем пустой файл для тестирования
            s3_client.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=b'{}'  # Пустой JSON
            )
            print(f"Created test object: {key}")
        
        print(f"Models bucket '{bucket_name}' initialized successfully")
        return True
        
    except Exception as e:
        print(f"Failed to create models bucket: {e}")
        return False

if __name__ == "__main__":
    create_models_bucket()
