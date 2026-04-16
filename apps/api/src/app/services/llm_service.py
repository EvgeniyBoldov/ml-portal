"""
LLM Service - AI content generation for versions
"""
import json
import logging
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.model_registry import Model
from app.adapters.impl.llm_client import LLMClient

logger = logging.getLogger(__name__)


class LLMService:
    """Service for AI-powered content generation"""
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.llm_client = LLMClient()
    
    async def generate_version_content(
        self,
        entity_type: str,
        description: str,
        fields: List[str],
        field_descriptions: Dict[str, str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate content for version fields using LLM"""
        
        # Собрать prompt
        prompt = self._build_generation_prompt(
            entity_type=entity_type,
            description=description,
            fields=fields,
            field_descriptions=field_descriptions,
            context=context
        )
        
        # Вызвать LLM
        try:
            response = await self.llm_client.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "Ты - ассистент для создания версий агентов и инструментов. Отвечай только валидным JSON."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            # Распарсить JSON
            content = response.content.strip()
            
            # Извлечь JSON из ответа
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_content = content[json_start:json_end].strip()
            elif "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_content = content[json_start:json_end]
            else:
                raise ValueError("No JSON found in LLM response")
            
            filled_fields = json.loads(json_content)
            
            # Валидация и постобработка
            filled_fields = self._post_process_fields(
                fields=fields,
                filled_fields=filled_fields,
                entity_type=entity_type
            )
            
            return filled_fields
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Возвращаем пустые значения при ошибке
            return {field: "" for field in fields}
    
    async def generate_suggestions(
        self,
        entity_type: str,
        description: str,
        filled_fields: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[str]:
        """Generate improvement suggestions"""
        
        prompt = f"""
Проанализируй сгенерированный контент для {entity_type} и дай предложения по улучшению.

ОПИСАНИЕ: {description}

СГЕНЕРИРОВАННЫЕ ПОЛЯ:
{json.dumps(filled_fields, indent=2, ensure_ascii=False)}

КОНТЕКСТ:
{json.dumps(context, indent=2, ensure_ascii=False)}

Дай 3-5 предложений по улучшению:
1. Что можно добавить или уточнить
2. Какие поля стоит заполнить дополнительно  
3. Лучшие практики для этого типа {entity_type}

Верни предложения в виде JSON массива строк:
```json
["предложение 1", "предложение 2", "предложение 3"]
```
"""
        
        try:
            response = await self.llm_client.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "Ты - ассистент для анализа и улучшения контента. Отвечай только валидным JSON массивом."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.5,
                max_tokens=500
            )
            
            content = response.content.strip()
            
            # Извлечь JSON массив
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_content = content[json_start:json_end].strip()
            elif "[" in content and "]" in content:
                json_start = content.find("[")
                json_end = content.rfind("]") + 1
                json_content = content[json_start:json_end]
            else:
                return []
            
            suggestions = json.loads(json_content)
            
            # Убедимся что это список строк
            if isinstance(suggestions, list):
                return [str(s) for s in suggestions if s]
            
            return []
            
        except Exception as e:
            logger.error(f"Suggestions generation failed: {e}")
            return []
    
    def _build_generation_prompt(
        self,
        entity_type: str,
        description: str,
        fields: List[str],
        field_descriptions: Dict[str, str],
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for LLM generation"""
        
        entity_name = "агента" if entity_type == "agent" else "инструмента"
        
        prompt = f"""
Ты - ассистент для создания версий {entity_name}. 

ЗАДАЧА: Заполни поля для новой версии {entity_name} на основе описания.

ОПИСАНИЕ {entity_name.upper()}:
{description}

ДОСТУПНЫЕ ПОЛЯ ДЛЯ ЗАПОЛНЕНИЯ:
"""
        
        # Добавить описания полей
        for field in fields:
            if field in field_descriptions:
                prompt += f"- {field}: {field_descriptions[field]}\n"
        
        prompt += f"""
КОНТЕКСТ:
{json.dumps(context, indent=2, ensure_ascii=False)}

ПРАВИЛА:
1. Заполни только указанные поля
2. Используй релевантные значения на основе описания
3. Для полей с массивами используй JSON формат
4. Для boolean полей используй true/false
5. Для числовых полей используй числа
6. Оставь поля пустыми если не можешь сгенерировать релевантное значение

Верни результат в виде JSON объекта с заполненными полями:
```json
{{
"""
        
        # Добавить шаблон полей
        field_templates = []
        for field in fields:
            if field in ["examples", "routing_ops", 
                        "routing_systems",
                        "routing_keywords", "routing_negative_keywords", "exec_retry_on"]:
                field_templates.append(f'  "{field}": []')
            elif field in ["tags"]:
                field_templates.append(f'  "{field}": []')
            elif field in ["routing_requires_confirmation", "routing_idempotent"]:
                field_templates.append(f'  "{field}": false')
            elif field in ["exec_timeout_s", "exec_max_retries", "exec_retry_backoff", 
                          "exec_max_concurrency"]:
                field_templates.append(f'  "{field}": 30')
            elif field in ["routing_risk_level", "exec_priority"]:
                field_templates.append(f'  "{field}": "medium"')
            else:
                field_templates.append(f'  "{field}": ""')
        
        prompt += ",\n".join(field_templates)
        prompt += "\n}"
        prompt += "\n```\n"
        
        return prompt
    
    def _post_process_fields(
        self,
        fields: List[str],
        filled_fields: Dict[str, Any],
        entity_type: str
    ) -> Dict[str, Any]:
        """Post-process and validate generated fields"""
        
        processed = {}
        
        for field in fields:
            if field not in filled_fields:
                processed[field] = ""
                continue
            
            value = filled_fields[field]
            
            # Типизация полей
            if field in ["examples", "routing_ops", 
                        "routing_systems",
                        "routing_keywords", "routing_negative_keywords", "exec_retry_on", "tags"]:
                # Ожидаем массив
                if isinstance(value, str):
                    try:
                        processed[field] = json.loads(value)
                    except:
                        processed[field] = [value] if value else []
                elif isinstance(value, list):
                    processed[field] = value
                else:
                    processed[field] = []
                    
            elif field in ["routing_requires_confirmation", "routing_idempotent"]:
                # Ожидаем boolean
                if isinstance(value, bool):
                    processed[field] = value
                elif isinstance(value, str):
                    processed[field] = value.lower() in ["true", "1", "yes"]
                else:
                    processed[field] = False
                    
            elif field in ["exec_timeout_s", "exec_max_retries", "exec_retry_backoff", 
                          "exec_max_concurrency"]:
                # Ожидаем число
                if isinstance(value, (int, float)):
                    processed[field] = int(value)
                elif isinstance(value, str):
                    try:
                        processed[field] = int(value)
                    except:
                        processed[field] = 30
                else:
                    processed[field] = 30
                    
            elif field in ["routing_risk_level", "exec_priority"]:
                # Ожидаем строку с определенными значениями
                if isinstance(value, str):
                    processed[field] = value
                else:
                    processed[field] = "medium"
                    
            else:
                # Ожидаем строку
                processed[field] = str(value) if value is not None else ""
        
        return processed
