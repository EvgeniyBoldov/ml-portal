# Модели

## Обзор

Система поддерживает два типа моделей:
- **LLM** — языковые модели для генерации
- **Embedding** — модели для векторизации

## LLM модели

### Внешние провайдеры

#### Groq

```bash
# .env
LLM_PROVIDER=groq
LLM_API_KEY=gsk_...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile
```

#### OpenAI

```bash
# .env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

#### Azure OpenAI

```bash
# .env
LLM_PROVIDER=azure
LLM_API_KEY=...
LLM_BASE_URL=https://your-resource.openai.azure.com
LLM_MODEL=gpt-4
LLM_API_VERSION=2024-02-15-preview
```

### Локальные модели

#### vLLM

```yaml
# docker-compose.yml
llm:
  image: vllm/vllm-openai:latest
  environment:
    - MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
  volumes:
    - llm_models:/root/.cache/huggingface
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

```bash
# .env
LLM_PROVIDER=local
LLM_BASE_URL=http://llm:8000/v1
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

#### Ollama

```yaml
# docker-compose.yml
llm:
  image: ollama/ollama:latest
  volumes:
    - ollama_data:/root/.ollama
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

```bash
# Загрузка модели
docker compose exec llm ollama pull llama3.1:8b

# .env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://llm:11434
LLM_MODEL=llama3.1:8b
```

## Embedding модели

### Text Embeddings Inference (TEI)

```yaml
# docker-compose.yml
emb:
  image: ghcr.io/huggingface/text-embeddings-inference:latest
  environment:
    - MODEL_ID=intfloat/multilingual-e5-small
  volumes:
    - emb_models:/data
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

```bash
# .env
EMB_BASE_URL=http://emb:80
EMB_MODEL=intfloat/multilingual-e5-small
```

### Рекомендуемые модели

| Модель | Размер | Языки | Dim |
|--------|--------|-------|-----|
| `intfloat/multilingual-e5-small` | 471MB | Multi | 384 |
| `intfloat/multilingual-e5-base` | 1.1GB | Multi | 768 |
| `intfloat/multilingual-e5-large` | 2.2GB | Multi | 1024 |
| `BAAI/bge-m3` | 2.2GB | Multi | 1024 |

## Добавление модели в БД

### Через миграцию

```python
# migrations/versions/XXXX_add_model.py
def upgrade():
    op.execute("""
        INSERT INTO models (id, alias, type, status, config, extra_config)
        VALUES (
            gen_random_uuid(),
            'qwen-7b',
            'llm',
            'active',
            '{"provider": "local", "model": "Qwen/Qwen2.5-7B-Instruct"}',
            '{"max_tokens": 4096, "temperature": 0.7}'
        )
    """)
```

### Через API

```bash
curl -X POST http://localhost:8000/api/v1/admin/models \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "qwen-7b",
    "type": "llm",
    "status": "active",
    "config": {
      "provider": "local",
      "model": "Qwen/Qwen2.5-7B-Instruct"
    },
    "extra_config": {
      "max_tokens": 4096,
      "temperature": 0.7
    }
  }'
```

### Через админку

1. Перейти в Admin → Models
2. Нажать "Add Model"
3. Заполнить форму
4. Сохранить

## Модель по умолчанию

### LLM

```sql
UPDATE models 
SET default_for_type = true 
WHERE alias = 'qwen-7b' AND type = 'llm';

-- Сбросить у других
UPDATE models 
SET default_for_type = false 
WHERE alias != 'qwen-7b' AND type = 'llm';
```

### Embedding

```sql
UPDATE models 
SET default_for_type = true 
WHERE alias = 'e5-small' AND type = 'embedding';
```

## Дополнительная embedding модель для тенанта

```sql
UPDATE tenants 
SET embedding_model_alias = 'e5-large' 
WHERE slug = 'department-a';
```

Документы тенанта будут индексироваться двумя моделями:
1. Глобальная (default)
2. Дополнительная (tenant-specific)

## Проверка работоспособности

### LLM

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

### Embedding

```bash
curl http://localhost:8002/embed \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": ["Hello, world!"]
  }'
```

## GPU Requirements

| Модель | VRAM |
|--------|------|
| Qwen2.5-7B | 16GB |
| Qwen2.5-14B | 32GB |
| Llama-3.1-8B | 16GB |
| Llama-3.1-70B | 140GB (multi-GPU) |
| e5-small | 2GB |
| e5-large | 4GB |

## CPU Fallback

Для работы без GPU:

```yaml
# docker-compose.cpu.yml
emb:
  image: ghcr.io/huggingface/text-embeddings-inference:cpu-latest
  environment:
    - MODEL_ID=intfloat/multilingual-e5-small
```

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
```
