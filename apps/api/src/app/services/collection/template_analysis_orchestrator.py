from __future__ import annotations

import uuid


class TemplateAnalysisOrchestrator:
    """Small Celery dispatch façade for template post-upload analysis."""

    @staticmethod
    def enqueue_description(
        *,
        collection_id: uuid.UUID | str,
        row_id: uuid.UUID | str,
        countdown: int = 1,
    ) -> str:
        from app.workers.tasks_template_analysis import generate_template_description

        result = generate_template_description.apply_async(
            args=[str(collection_id), str(row_id)],
            countdown=countdown,
        )
        return str(result.id)

    @staticmethod
    def enqueue_schema(
        *,
        collection_id: uuid.UUID | str,
        row_id: uuid.UUID | str,
        countdown: int = 1,
    ) -> str:
        from app.workers.tasks_template_analysis import generate_template_schema

        result = generate_template_schema.apply_async(
            args=[str(collection_id), str(row_id)],
            countdown=countdown,
        )
        return str(result.id)

    @classmethod
    def enqueue_all(
        cls,
        *,
        collection_id: uuid.UUID | str,
        row_id: uuid.UUID | str,
        countdown: int = 1,
    ) -> dict[str, str]:
        return {
            "description_task_id": cls.enqueue_description(
                collection_id=collection_id,
                row_id=row_id,
                countdown=countdown,
            ),
            "schema_task_id": cls.enqueue_schema(
                collection_id=collection_id,
                row_id=row_id,
                countdown=countdown,
            ),
        }
