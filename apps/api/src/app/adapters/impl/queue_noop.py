
import uuid
from ...core.config import get_settings

class NoopQueueClient:
    def enqueue(self, task: str, payload: dict) -> str:
        task_id = str(uuid.uuid4())
        # here we would publish to Celery/RabbitMQ; left as stub
        return task_id

    def cancel(self, task_id: str) -> None:
        # noop
        return None
