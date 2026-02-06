"""
Утилита для вычисления schema_hash — SHA256 от canonical JSON schemas.

Используется для:
- Observability: отслеживание изменений схем между деплоями
- Валидация: детект schema drift между backend release и tool release
- Autodiscovery: определение breaking changes при sync
"""
import hashlib
import json
from typing import Any, Dict, Optional


def compute_schema_hash(
    input_schema: Dict[str, Any],
    output_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Вычислить SHA256 от canonical JSON {input_schema, output_schema}.
    
    Canonical = sorted keys, no whitespace, ensure_ascii=False.
    Гарантирует одинаковый hash для одинаковых схем
    независимо от порядка ключей в dict.
    
    Args:
        input_schema: JSON Schema для входных параметров
        output_schema: JSON Schema для выходных данных (опционально)
        
    Returns:
        64-символьный hex SHA256 hash
    """
    payload = {
        "input": input_schema,
        "output": output_schema,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_schema_diff(
    old_schema: Dict[str, Any],
    new_schema: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Вычислить diff между двумя input_schema (JSON Schema format).
    
    Сравнивает properties верхнего уровня.
    
    Returns:
        {
            "added_fields": [{"name": str, "type": str, "required": bool}],
            "removed_fields": [{"name": str, "type": str, "required": bool}],
            "changed_fields": [{"name": str, "old_type": str, "new_type": str}],
        }
    """
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))
    
    old_keys = set(old_props.keys())
    new_keys = set(new_props.keys())
    
    added = new_keys - old_keys
    removed = old_keys - new_keys
    common = old_keys & new_keys
    
    added_fields = [
        {
            "name": k,
            "type": new_props[k].get("type", "unknown"),
            "required": k in new_required,
            "description": new_props[k].get("description", ""),
        }
        for k in sorted(added)
    ]
    
    removed_fields = [
        {
            "name": k,
            "type": old_props[k].get("type", "unknown"),
            "required": k in old_required,
        }
        for k in sorted(removed)
    ]
    
    changed_fields = []
    for k in sorted(common):
        old_type = old_props[k].get("type", "unknown")
        new_type = new_props[k].get("type", "unknown")
        if old_type != new_type:
            changed_fields.append({
                "name": k,
                "old_type": old_type,
                "new_type": new_type,
            })
    
    return {
        "added_fields": added_fields,
        "removed_fields": removed_fields,
        "changed_fields": changed_fields,
    }
