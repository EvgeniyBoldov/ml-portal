from fastapi import APIRouter, Depends
from app.schemas.models import AnalyzeRequest, AnalyzeResponse
from app.core.dependencies import current_user

router = APIRouter()

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_document(payload: AnalyzeRequest, user = Depends(current_user)):
    # Заглушка анализа документа
    return AnalyzeResponse(
        summary=f"Анализ документа {payload.document_id}: пока заглушка.",
        references=[{"id": payload.document_id, "score": 0.99}],
    )

