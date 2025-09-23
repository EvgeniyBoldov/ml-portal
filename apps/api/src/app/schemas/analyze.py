from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    text: str

class AnalyzeResult(BaseModel):
    result: str
