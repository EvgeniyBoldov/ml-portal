"""
Chat message content unification and validation
"""
from __future__ import annotations
from typing import Dict, Any, Union, Optional
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class MessageContentType(str, Enum):
    """Standard message content types"""
    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    CODE = "code"
    IMAGE = "image"
    FILE = "file"


class MessageContentPart(BaseModel):
    """Single part of message content"""
    type: MessageContentType = Field(..., description="Content type")
    content: str = Field(..., description="Content text")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    model_config = {"from_attributes": True}


class UnifiedMessageContent(BaseModel):
    """Unified message content format"""
    type: MessageContentType = Field(default=MessageContentType.TEXT, description="Primary content type")
    parts: list[MessageContentPart] = Field(..., description="Content parts")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Global metadata")
    
    model_config = {"from_attributes": True}
    
    @field_validator('parts')
    @classmethod
    def validate_parts(cls, v):
        if not v:
            raise ValueError("Message content must have at least one part")
        return v


class MessageContentConverter:
    """Converter for legacy message content formats"""
    
    @staticmethod
    def from_legacy_dict(content: Dict[str, Any]) -> UnifiedMessageContent:
        """Convert legacy dict format to unified format"""
        if "text" in content:
            # Legacy format: {"text": "content"}
            return UnifiedMessageContent(
                type=MessageContentType.TEXT,
                parts=[MessageContentPart(
                    type=MessageContentType.TEXT,
                    content=content["text"],
                    metadata=content.get("metadata")
                )],
                metadata=content.get("meta")
            )
        elif "type" in content and "content" in content:
            # Already unified format
            return UnifiedMessageContent(
                type=MessageContentType(content["type"]),
                parts=[MessageContentPart(
                    type=MessageContentType(content["type"]),
                    content=content["content"],
                    metadata=content.get("metadata")
                )],
                metadata=content.get("meta")
            )
        else:
            # Unknown format - treat as text
            return UnifiedMessageContent(
                type=MessageContentType.TEXT,
                parts=[MessageContentPart(
                    type=MessageContentType.TEXT,
                    content=str(content),
                    metadata={"legacy_format": True}
                )]
            )
    
    @staticmethod
    def from_legacy_string(content: str) -> UnifiedMessageContent:
        """Convert legacy string format to unified format"""
        return UnifiedMessageContent(
            type=MessageContentType.TEXT,
            parts=[MessageContentPart(
                type=MessageContentType.TEXT,
                content=content
            )]
        )
    
    @staticmethod
    def to_legacy_dict(content: UnifiedMessageContent) -> Dict[str, Any]:
        """Convert unified format to legacy dict format"""
        if len(content.parts) == 1 and content.parts[0].type == MessageContentType.TEXT:
            # Simple text message
            result = {"text": content.parts[0].content}
            if content.parts[0].metadata:
                result["metadata"] = content.parts[0].metadata
            if content.metadata:
                result["meta"] = content.metadata
            return result
        else:
            # Complex message - return unified format
            return content.model_dump()
    
    @staticmethod
    def to_legacy_string(content: UnifiedMessageContent) -> str:
        """Convert unified format to legacy string format"""
        if len(content.parts) == 1 and content.parts[0].type == MessageContentType.TEXT:
            return content.parts[0].content
        else:
            # Complex message - return JSON string
            return content.model_dump_json()


class MessageContentValidator:
    """Validator for message content"""
    
    @staticmethod
    def validate_content(content: Union[str, Dict[str, Any], UnifiedMessageContent]) -> UnifiedMessageContent:
        """Validate and normalize message content"""
        if isinstance(content, str):
            return MessageContentConverter.from_legacy_string(content)
        elif isinstance(content, dict):
            return MessageContentConverter.from_legacy_dict(content)
        elif isinstance(content, UnifiedMessageContent):
            return content
        else:
            raise ValueError(f"Unsupported content type: {type(content)}")
    
    @staticmethod
    def validate_text_content(content: str, max_length: int = 10000) -> str:
        """Validate text content"""
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")
        
        if len(content) > max_length:
            raise ValueError(f"Content too long: {len(content)} > {max_length}")
        
        return content.strip()
    
    @staticmethod
    def validate_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate metadata"""
        if metadata is None:
            return None
        
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")
        
        # Remove None values
        return {k: v for k, v in metadata.items() if v is not None}


class MessageContentMigration:
    """Migration utilities for message content"""
    
    @staticmethod
    def migrate_legacy_content(content: Union[str, Dict[str, Any]]) -> UnifiedMessageContent:
        """Migrate legacy content to unified format"""
        return MessageContentValidator.validate_content(content)
    
    @staticmethod
    def create_text_message(text: str, metadata: Optional[Dict[str, Any]] = None) -> UnifiedMessageContent:
        """Create a simple text message"""
        validated_text = MessageContentValidator.validate_text_content(text)
        validated_metadata = MessageContentValidator.validate_metadata(metadata)
        
        return UnifiedMessageContent(
            type=MessageContentType.TEXT,
            parts=[MessageContentPart(
                type=MessageContentType.TEXT,
                content=validated_text,
                metadata=validated_metadata
            )]
        )
    
    @staticmethod
    def create_markdown_message(markdown: str, metadata: Optional[Dict[str, Any]] = None) -> UnifiedMessageContent:
        """Create a markdown message"""
        validated_text = MessageContentValidator.validate_text_content(markdown)
        validated_metadata = MessageContentValidator.validate_metadata(metadata)
        
        return UnifiedMessageContent(
            type=MessageContentType.MARKDOWN,
            parts=[MessageContentPart(
                type=MessageContentType.MARKDOWN,
                content=validated_text,
                metadata=validated_metadata
            )]
        )
    
    @staticmethod
    def create_code_message(code: str, language: str = "text", metadata: Optional[Dict[str, Any]] = None) -> UnifiedMessageContent:
        """Create a code message"""
        validated_text = MessageContentValidator.validate_text_content(code)
        validated_metadata = MessageContentValidator.validate_metadata(metadata)
        
        if validated_metadata is None:
            validated_metadata = {}
        
        validated_metadata["language"] = language
        
        return UnifiedMessageContent(
            type=MessageContentType.CODE,
            parts=[MessageContentPart(
                type=MessageContentType.CODE,
                content=validated_text,
                metadata=validated_metadata
            )]
        )
