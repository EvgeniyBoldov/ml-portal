from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION = (
    "Необходимо вызвать хотя бы одну операцию перед ответом. "
    "Не отвечай по памяти — используй результаты операций. "
    "Выбери наиболее подходящую операцию и верни operation_call."
)

PLATFORM_OPERATION_RULES_TEXT = (
    "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА — соблюдай без исключений:\n"
    "1. Если пользователь запрашивает РЕАЛЬНЫЕ ДАННЫЕ (записи, значения, количества, статусы, конфигурацию) — сначала вызови операцию. Не отвечай по памяти.\n"
    "2. ИСКЛЮЧЕНИЕ: если вопрос только о том, какие источники данных или операции доступны (мета-вопрос о возможностях) — можно ответить напрямую из capability card.\n"
    "3. Финальный ответ на вопросы о данных — только после получения результатов операций.\n"
    "4. Не придумывай значения — используй только данные из операций."
)

PLATFORM_INTENT_MESSAGES: Dict[str, str] = {
    "agent_start": "Запускаю выполнение агента",
    "final_answer": "Формирую финальный ответ",
    "operation_call": "Выполняю операцию: {operation_slug}",
}

PLATFORM_DEFAULT_MAX_ITERS = 25
PLATFORM_SYNTH_CHUNK_SIZE = 20

PLATFORM_FALLBACK_SETTINGS: Dict[str, Any] = {
    "required_operation_retry_instruction": PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION,
    "operations_rules_text": PLATFORM_OPERATION_RULES_TEXT,
    "intent_messages": PLATFORM_INTENT_MESSAGES,
    "default_max_iters": PLATFORM_DEFAULT_MAX_ITERS,
    "synth_chunk_size": PLATFORM_SYNTH_CHUNK_SIZE,
}


def _settings_to_dict(settings: Any) -> Dict[str, Any]:
    if settings is None:
        return {}
    if isinstance(settings, dict):
        return dict(settings)
    if hasattr(settings, "model_dump"):
        return settings.model_dump()
    if isinstance(settings, Mapping):
        return dict(settings)
    return {
        key: getattr(settings, key, None)
        for key in (
            "id",
            "policies_text",
            "require_confirmation_for_write",
            "require_confirmation_for_destructive",
            "forbid_destructive",
            "forbid_write_in_prod",
            "require_backup_before_write",
            "required_operation_retry_instruction",
            "default_max_iters",
            "operations_rules_text",
            "intent_messages",
            "synth_chunk_size",
            "chat_upload_max_bytes",
            "chat_upload_allowed_extensions",
            "created_at",
            "updated_at",
        )
    }


def build_effective_platform_settings_payload(settings: Any) -> Dict[str, Any]:
    payload = _settings_to_dict(settings)
    effective = dict(payload)
    for key, fallback in PLATFORM_FALLBACK_SETTINGS.items():
        current = effective.get(key)
        if current is None:
            effective[key] = deepcopy(fallback) if isinstance(fallback, dict) else fallback
    return effective


def build_platform_runtime_config(settings: Any) -> Dict[str, Any]:
    effective = build_effective_platform_settings_payload(settings)
    return {
        "policies_text": effective.get("policies_text"),
        "require_confirmation_for_write": bool(effective.get("require_confirmation_for_write") or False),
        "require_confirmation_for_destructive": bool(effective.get("require_confirmation_for_destructive") or False),
        "forbid_destructive": bool(effective.get("forbid_destructive") or False),
        "forbid_write_in_prod": bool(effective.get("forbid_write_in_prod") or False),
        "require_backup_before_write": bool(effective.get("require_backup_before_write") or False),
        "required_operation_retry_instruction": effective.get("required_operation_retry_instruction"),
        "default_max_iters": effective.get("default_max_iters"),
        "operations_rules_text": effective.get("operations_rules_text"),
        "intent_messages": effective.get("intent_messages"),
        "runtime": {
            "synth_chunk_size": effective.get("synth_chunk_size"),
            "default_max_iters": effective.get("default_max_iters"),
        },
        "chat_upload_max_bytes": effective.get("chat_upload_max_bytes"),
        "chat_upload_allowed_extensions": effective.get("chat_upload_allowed_extensions"),
    }


def apply_missing_platform_defaults(settings: Any) -> bool:
    """
    Fill missing platform settings fields in-place from Python defaults.
    Returns True when at least one field was updated.
    """
    changed = False
    for key, fallback in PLATFORM_FALLBACK_SETTINGS.items():
        current = getattr(settings, key, None)
        if current is None:
            setattr(settings, key, deepcopy(fallback) if isinstance(fallback, dict) else fallback)
            changed = True
    return changed
