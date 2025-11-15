# Миграция на RSA ключи для JWT

## Зачем это нужно?

**Критическая уязвимость:** Текущая реализация использует симметричный секрет (HS256) и публикует его в JWKS endpoint, что позволяет любому подделывать токены.

**Решение:** Переход на асимметричную криптографию (RS256) - публикуется только публичный ключ, приватный остается в секрете.

## Генерация RSA ключей

### 1. Генерация ключей (один раз для каждого окружения)

```bash
# Генерируем приватный ключ (2048 бит)
openssl genrsa -out jwt_private.pem 2048

# Извлекаем публичный ключ
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem

# Проверяем ключи
openssl rsa -in jwt_private.pem -check
openssl rsa -pubin -in jwt_public.pem -text -noout
```

### 2. Конвертация в формат для .env

```bash
# Приватный ключ (одна строка с \n)
awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' jwt_private.pem

# Публичный ключ (одна строка с \n)
awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' jwt_public.pem
```

## Настройка окружений

### Development (.env.dev)

```env
# JWT Configuration
JWT_ALGORITHM=HS256
JWT_SECRET=your-dev-secret-key-change-me
# RSA keys not required for dev (HS256)
```

### Staging/Production (.env.staging, .env.production)

```env
# JWT Configuration - RSA (REQUIRED)
JWT_ALGORITHM=RS256
JWT_KID=prod-key-2025-01  # Key ID for rotation

# Private key (keep SECRET, never commit!)
JWT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----\n"

# Public key (safe to publish in JWKS)
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...\n-----END PUBLIC KEY-----\n"

# Legacy secret (not used with RS256, but keep for fallback)
JWT_SECRET=legacy-secret-not-used
```

## Безопасное хранение ключей

### Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: jwt-keys
  namespace: ml-portal
type: Opaque
stringData:
  jwt_private_key: |
    -----BEGIN RSA PRIVATE KEY-----
    MIIEpAIBAAKCAQEA...
    -----END RSA PRIVATE KEY-----
  jwt_public_key: |
    -----BEGIN PUBLIC KEY-----
    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
    -----END PUBLIC KEY-----
```

### Docker Secrets

```bash
# Создаем secrets
docker secret create jwt_private_key jwt_private.pem
docker secret create jwt_public_key jwt_public.pem

# В docker-compose.yml
services:
  api:
    secrets:
      - jwt_private_key
      - jwt_public_key
    environment:
      JWT_PRIVATE_KEY_FILE: /run/secrets/jwt_private_key
      JWT_PUBLIC_KEY_FILE: /run/secrets/jwt_public_key
```

### AWS Secrets Manager / HashiCorp Vault

```python
# Пример загрузки из AWS Secrets Manager
import boto3
import json

def get_jwt_keys():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId='prod/jwt-keys')
    secrets = json.loads(response['SecretString'])
    return secrets['private_key'], secrets['public_key']
```

## Ротация ключей

### Процесс ротации (zero-downtime)

1. **Генерируем новую пару ключей**
   ```bash
   openssl genrsa -out jwt_private_new.pem 2048
   openssl rsa -in jwt_private_new.pem -pubout -out jwt_public_new.pem
   ```

2. **Публикуем оба публичных ключа в JWKS**
   ```env
   JWT_KID=prod-key-2025-02  # New key ID
   JWT_KID_OLD=prod-key-2025-01  # Old key ID (for verification)
   ```

3. **Период overlap (7-30 дней)**
   - Новые токены подписываются новым ключом
   - Старые токены проверяются старым ключом
   - Оба публичных ключа в JWKS

4. **Удаляем старый ключ**
   - После истечения всех старых токенов (JWT_ACCESS_TTL_MINUTES)
   - Убираем старый публичный ключ из JWKS

## Проверка работы

### 1. Проверка JWKS endpoint

```bash
# Должен вернуть публичный ключ в JWK формате
curl https://api.ml-portal.com/.well-known/jwks.json

# Ожидаемый ответ:
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "prod-key-2025-01",
      "use": "sig",
      "alg": "RS256",
      "n": "base64url_encoded_modulus...",
      "e": "AQAB"
    }
  ]
}
```

### 2. Проверка токена

```python
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Загружаем публичный ключ
with open('jwt_public.pem', 'rb') as f:
    public_key = serialization.load_pem_public_key(f.read(), backend=default_backend())

# Проверяем токен
token = "eyJ..."
payload = jwt.decode(token, public_key, algorithms=['RS256'], audience='urn:ml-portal:api')
print(payload)
```

### 3. Тест безопасности

```bash
# Попытка подделать токен с публичным ключом должна FAIL
# (в отличие от HS256, где это возможно)
```

## Troubleshooting

### Ошибка: "JWT_PRIVATE_KEY required for RS256"

**Причина:** Не установлен приватный ключ при JWT_ALGORITHM=RS256

**Решение:**
```env
JWT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
```

### Ошибка: "Invalid token signature"

**Причины:**
1. Токен подписан старым ключом, но используется новый
2. Неправильный формат ключа (лишние пробелы, неправильные \n)
3. Несоответствие алгоритма (токен RS256, но проверка HS256)

**Решение:** Проверить JWT_ALGORITHM и ключи в обоих окружениях

### Ошибка: "Unable to parse PEM key"

**Причина:** Неправильный формат ключа в .env

**Решение:** Убедиться что:
- Используются `\n` для переносов строк
- Нет лишних пробелов
- Ключ в кавычках: `JWT_PRIVATE_KEY="..."`

## Мониторинг

### Метрики для отслеживания

```python
# Prometheus metrics
jwt_tokens_issued_total{algorithm="RS256"}
jwt_tokens_verified_total{algorithm="RS256",result="success|failure"}
jwt_key_rotation_timestamp{kid="prod-key-2025-01"}
```

### Алерты

```yaml
- alert: JWTVerificationFailureRate
  expr: rate(jwt_tokens_verified_total{result="failure"}[5m]) > 0.1
  annotations:
    summary: "High JWT verification failure rate"
    
- alert: JWTKeyRotationOverdue
  expr: time() - jwt_key_rotation_timestamp > 90*24*3600
  annotations:
    summary: "JWT key rotation overdue (>90 days)"
```

## Чеклист миграции

- [ ] Сгенерированы RSA ключи для staging
- [ ] Сгенерированы RSA ключи для production
- [ ] Ключи сохранены в secrets manager
- [ ] Обновлены .env файлы
- [ ] JWT_ALGORITHM=RS256 в production
- [ ] Протестирован JWKS endpoint
- [ ] Протестирована генерация токенов
- [ ] Протестирована проверка токенов
- [ ] Обновлена документация
- [ ] Настроен мониторинг
- [ ] Запланирована первая ротация ключей (через 90 дней)

## Дополнительные ресурсы

- [RFC 7517 - JSON Web Key (JWK)](https://tools.ietf.org/html/rfc7517)
- [RFC 7518 - JSON Web Algorithms (JWA)](https://tools.ietf.org/html/rfc7518)
- [JWT.io - Debugger](https://jwt.io/)
- [PyJWT Documentation](https://pyjwt.readthedocs.io/)
