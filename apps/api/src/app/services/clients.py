
from ..adapters.impl.llm_http import HttpLLMClient
from ..adapters.impl.emb_http import HttpEmbeddingsClient
from ..adapters.impl.qdrant import QdrantVectorStore
from ..adapters.impl.s3_minio import MinioStorage

class Clients:
    def __init__(self):
        self.llm = HttpLLMClient()
        self.emb = HttpEmbeddingsClient()
        self.vs = QdrantVectorStore()
        self.s3 = MinioStorage()
