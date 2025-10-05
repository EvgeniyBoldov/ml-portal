from __future__ import annotations
import asyncio
import time
from typing import Any, Callable, Dict, Optional, TypeVar
from enum import Enum
import logging
from core.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar('T')

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service is back

class CircuitBreaker:
    """Circuit breaker for external service calls"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        name: str = "circuit_breaker"
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.name = name
        
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = CircuitState.CLOSED
        self.half_open_calls = 0
    
    def can_execute(self) -> bool:
        """Check if circuit allows execution"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info(f"Circuit {self.name} transitioning to HALF_OPEN")
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        
        return False
    
    def record_success(self):
        """Record successful execution"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            logger.info(f"Circuit {self.name} transitioning to CLOSED")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed execution"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.info(f"Circuit {self.name} transitioning to OPEN")
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name} transitioning to OPEN after {self.failure_count} failures")
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection"""
        if not self.can_execute():
            raise CircuitBreakerOpenError(f"Circuit {self.name} is OPEN")
        
        try:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
            
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self.record_success()
            return result
        
        except Exception as e:
            self.record_failure()
            raise

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass

class RetryConfig:
    """Configuration for retry logic"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

class ResilienceManager:
    """Manages resilience features for external services"""
    
    def __init__(self):
        self.settings = get_settings()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.retry_configs: Dict[str, RetryConfig] = {}
        self._setup_defaults()
    
    def _setup_defaults(self):
        """Setup default circuit breakers and retry configs"""
        # LLM service circuit breaker
        self.circuit_breakers['llm'] = CircuitBreaker(
            failure_threshold=self.settings.CB_LLM_FAILURES_THRESHOLD,
            recovery_timeout=self.settings.CB_LLM_OPEN_TIMEOUT_SECONDS,
            half_open_max_calls=self.settings.CB_LLM_HALF_OPEN_MAX_CALLS,
            name="llm_service"
        )
        
        # Embedding service circuit breaker
        self.circuit_breakers['emb'] = CircuitBreaker(
            failure_threshold=self.settings.CB_EMB_FAILURES_THRESHOLD,
            recovery_timeout=self.settings.CB_EMB_OPEN_TIMEOUT_SECONDS,
            half_open_max_calls=self.settings.CB_EMB_HALF_OPEN_MAX_CALLS,
            name="emb_service"
        )
        
        # Default retry config
        self.retry_configs['default'] = RetryConfig(
            max_retries=self.settings.HTTP_MAX_RETRIES,
            base_delay=1.0,
            max_delay=30.0
        )
    
    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """Get circuit breaker for service"""
        return self.circuit_breakers.get(service_name, self.circuit_breakers['llm'])
    
    def get_retry_config(self, service_name: str) -> RetryConfig:
        """Get retry config for service"""
        return self.retry_configs.get(service_name, self.retry_configs['default'])
    
    async def execute_with_resilience(
        self,
        func: Callable[..., T],
        service_name: str = "default",
        *args,
        **kwargs
    ) -> T:
        """Execute function with circuit breaker and retry logic"""
        circuit_breaker = self.get_circuit_breaker(service_name)
        retry_config = self.get_retry_config(service_name)
        
        last_exception = None
        
        for attempt in range(retry_config.max_retries + 1):
            try:
                return await circuit_breaker.call(func, *args, **kwargs)
            
            except CircuitBreakerOpenError:
                raise
            
            except Exception as e:
                last_exception = e
                
                if attempt == retry_config.max_retries:
                    logger.error(f"All retry attempts failed for {service_name}: {e}")
                    break
                
                # Calculate delay with exponential backoff
                delay = min(
                    retry_config.base_delay * (retry_config.exponential_base ** attempt),
                    retry_config.max_delay
                )
                
                if retry_config.jitter:
                    import random
                    delay *= (0.5 + random.random() * 0.5)
                
                logger.warning(f"Retry {attempt + 1}/{retry_config.max_retries} for {service_name} in {delay:.2f}s: {e}")
                await asyncio.sleep(delay)
        
        raise last_exception

# Global resilience manager
resilience_manager = ResilienceManager()

async def execute_with_resilience(
    func: Callable[..., T],
    service_name: str = "default",
    *args,
    **kwargs
) -> T:
    """Execute function with resilience features"""
    return await resilience_manager.execute_with_resilience(func, service_name, *args, **kwargs)
