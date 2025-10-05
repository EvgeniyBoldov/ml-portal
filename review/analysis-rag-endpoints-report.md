# Отчет о проверке эндпоинтов анализа и RAG

## 🔍 Анализ эндпоинтов

### ✅ Доступные эндпоинты в бэкенде:

#### Анализ (`/api/v1/analyze/`):
- `POST /api/v1/analyze/ingest/presign` - получение presigned URL для загрузки
- `POST /api/v1/analyze/stream` - стриминг анализа текстов

#### RAG (`/api/v1/rag/`):
- `POST /api/v1/rag/upload/presign` - получение presigned URL для загрузки документов

### ❌ Проблемы с фронтендом:

#### Анализ (`apps/web/src/shared/api/analyze.ts`):
```typescript
// ❌ НЕ СУЩЕСТВУЕТ в бэкенде:
export async function listAnalyze() {
  return apiRequest<{ items: any[] }>('/analyze');  // GET /analyze
}

export async function uploadAnalysisFile(file: File) {
  return apiRequest<{ id: string; status: string }>('/analyze/upload', {  // POST /analyze/upload
    method: 'POST',
    body: fd,
  });
}

export async function getAnalyze(id: string) {
  return apiRequest<any>(`/analyze/${id}`);  // GET /analyze/{id}
}

export async function downloadAnalysisFile(doc_id: string, kind: 'original' | 'canonical' = 'original') {
  return apiRequest<{ url: string }>(`/analyze/${doc_id}/download?kind=${kind}`);  // GET /analyze/{id}/download
}

export async function deleteAnalysisFile(doc_id: string) {
  return apiRequest<{ id: string; deleted: boolean }>(`/analyze/${doc_id}`, {  // DELETE /analyze/{id}
    method: 'DELETE',
  });
}

export async function reanalyzeFile(doc_id: string) {
  return apiRequest<{ id: string; status: string }>(`/analyze/${doc_id}/reanalyze`, {  // POST /analyze/{id}/reanalyze
    method: 'POST'
  });
}
```

#### RAG (`apps/web/src/shared/api/rag.ts`):
```typescript
// ❌ НЕ СУЩЕСТВУЕТ в бэкенде:
export async function listDocs(params: {...}) {
  return apiRequest<{...}>(`/rag/?${qs.toString()}`);  // GET /rag/
}

export async function uploadFile(file: File, name?: string, tags?: string[]) {
  return apiRequest<{ id: string; status: string }>('/rag/upload', {  // POST /rag/upload
    method: 'POST',
    body: fd,
  });
}

export async function updateRagDocumentTags(docId: string, tags: string[]) {
  return apiRequest<{ id: string; tags: string[] }>(`/rag/${docId}/tags`, {  // PUT /rag/{id}/tags
    method: 'PUT',
    body: JSON.stringify(tags),
  });
}

export async function getRagProgress(doc_id: string) {
  return apiRequest<any>(`/rag/${doc_id}/progress`);  // GET /rag/{id}/progress
}

export async function getRagStats() {
  return apiRequest<any>('/rag/stats');  // GET /rag/stats
}

export async function getRagMetrics() {
  return apiRequest<any>('/rag/metrics');  // GET /rag/metrics
}

export async function downloadRagFile(doc_id: string, kind: 'original' | 'canonical' = 'original') {
  return apiRequest<{ url: string }>(`/rag/${doc_id}/download?kind=${kind}`);  // GET /rag/{id}/download
}

export async function archiveRagDocument(doc_id: string) {
  return apiRequest<{ id: string; archived: boolean }>(`/rag/${doc_id}/archive`, {  // POST /rag/{id}/archive
    method: 'POST'
  });
}

export async function deleteRagDocument(doc_id: string) {
  return apiRequest<{ id: string; deleted: boolean }>(`/rag/${doc_id}`, {  // DELETE /rag/{id}
    method: 'DELETE',
  });
}

export async function ragSearch(payload: {...}) {
  return apiRequest<{...}>('/rag/search', {  // POST /rag/search
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function reindexRagDocument(doc_id: string) {
  return apiRequest<{ id: string; status: string }>(`/rag/${doc_id}/reindex`, {  // POST /rag/{id}/reindex
    method: 'POST',
  });
}

export async function reindexAllRagDocuments() {
  return apiRequest<{ reindexed_count: number; total_documents: number }>('/rag/reindex', {  // POST /rag/reindex
    method: 'POST'
  });
}
```

## 🚨 Проблемы:

### 1. **Анализ**: Фронтенд ожидает 6 эндпоинтов, бэкенд предоставляет только 2
- ❌ `GET /analyze` - список анализов
- ❌ `POST /analyze/upload` - загрузка файла
- ❌ `GET /analyze/{id}` - получение анализа
- ❌ `GET /analyze/{id}/download` - скачивание файла
- ❌ `DELETE /analyze/{id}` - удаление анализа
- ❌ `POST /analyze/{id}/reanalyze` - переанализ

### 2. **RAG**: Фронтенд ожидает 12 эндпоинтов, бэкенд предоставляет только 1
- ❌ `GET /rag/` - список документов
- ❌ `POST /rag/upload` - загрузка файла
- ❌ `PUT /rag/{id}/tags` - обновление тегов
- ❌ `GET /rag/{id}/progress` - прогресс обработки
- ❌ `GET /rag/stats` - статистика
- ❌ `GET /rag/metrics` - метрики
- ❌ `GET /rag/{id}/download` - скачивание файла
- ❌ `POST /rag/{id}/archive` - архивирование
- ❌ `DELETE /rag/{id}` - удаление документа
- ❌ `POST /rag/search` - поиск
- ❌ `POST /rag/{id}/reindex` - переиндексация
- ❌ `POST /rag/reindex` - переиндексация всех

### 3. **Технические проблемы**:
- RAG эндпоинт `/api/v1/rag/upload/presign` падает с ошибкой `AttributeError: 'int' object has no attribute 'total_seconds'`
- Анализ эндпоинт `/api/v1/analyze/ingest/presign` требует параметр `request` в query

## 📋 Рекомендации:

1. **Исправить технические ошибки** в бэкенде
2. **Реализовать недостающие эндпоинты** или **обновить фронтенд** под существующие
3. **Добавить mock данные** для разработки
4. **Обновить документацию** OpenAPI
