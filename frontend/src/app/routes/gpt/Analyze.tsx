import React, { useState, useEffect } from 'react';
import Card from '@shared/ui/Card';
import Button from '@shared/ui/Button';
import FilePicker from '@shared/ui/FilePicker';
import * as analyze from '@shared/api/analyze';
import { AnalyzeDocument } from '@shared/api/types';
import styles from './AnalyzePage.module.css';

export default function Analyze() {
  const [documents, setDocuments] = useState<AnalyzeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const res = await analyze.listAnalyze();
      setDocuments(res.items || []);
    } catch (error) {
      console.error('Failed to load documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    try {
      await analyze.uploadAnalysisFile(file);
      await loadDocuments();
    } catch (error) {
      console.error('Failed to upload file:', error);
      alert('Ошибка загрузки файла');
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (
    doc: AnalyzeDocument,
    kind: 'original' | 'canonical' = 'original'
  ) => {
    try {
      const res = await analyze.downloadAnalysisFile(doc.id, kind);
      if (res.url) {
        window.open(res.url, '_blank');
      }
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const handleDelete = async (doc: AnalyzeDocument) => {
    if (!confirm('Удалить документ?')) return;
    try {
      await analyze.deleteAnalysisFile(doc.id);
      await loadDocuments();
    } catch (error) {
      console.error('Delete failed:', error);
      alert('Ошибка удаления документа');
    }
  };

  const handleReanalyze = async (doc: AnalyzeDocument) => {
    if (!confirm('Повторно проанализировать документ?')) return;
    try {
      await analyze.reanalyzeFile(doc.id);
      await loadDocuments();
    } catch (error) {
      console.error('Reanalyze failed:', error);
      alert('Ошибка повторного анализа');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'done':
        return '#4caf50';
      case 'processing':
        return '#ff9800';
      case 'error':
        return '#f44336';
      case 'canceled':
        return '#9e9e9e';
      default:
        return '#2196f3';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'queued':
        return 'В очереди';
      case 'processing':
        return 'Обработка';
      case 'done':
        return 'Готов';
      case 'error':
        return 'Ошибка';
      case 'canceled':
        return 'Отменен';
      default:
        return status;
    }
  };

  return (
    <div className={styles.container}>
      <Card className={styles.uploadCard}>
        <h3>Загрузка файла для анализа</h3>
        <FilePicker
          onFileSelected={file => file && handleFileUpload(file)}
          accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt"
          disabled={uploading}
        />
        {uploading && <p>Загрузка...</p>}
      </Card>

      <Card className={styles.documentsCard}>
        <h3>Документы на анализе ({documents.length})</h3>
        {loading ? (
          <p>Загрузка...</p>
        ) : documents.length === 0 ? (
          <p>Нет документов</p>
        ) : (
          <div className={styles.documentsList}>
            {documents.map(doc => (
              <div key={doc.id} className={styles.documentItem}>
                <div className={styles.documentInfo}>
                  <div className={styles.documentName}>
                    Документ {doc.id.slice(0, 8)}
                  </div>
                  <div className={styles.documentStatus}>
                    <span
                      className={styles.statusBadge}
                      style={{ backgroundColor: getStatusColor(doc.status) }}
                    >
                      {getStatusText(doc.status)}
                    </span>
                    {doc.error && (
                      <span className={styles.errorText}>{doc.error}</span>
                    )}
                  </div>
                  <div className={styles.documentDate}>
                    {doc.date_upload &&
                      new Date(doc.date_upload).toLocaleString()}
                  </div>
                  {doc.result && (
                    <div className={styles.resultPreview}>
                      <strong>Результат:</strong>
                      <pre>{JSON.stringify(doc.result, null, 2)}</pre>
                    </div>
                  )}
                </div>
                <div className={styles.documentActions}>
                  {doc.status === 'done' && (
                    <>
                      <Button
                        size="small"
                        onClick={() => handleDownload(doc, 'original')}
                      >
                        Скачать оригинал
                      </Button>
                      {doc.url_canonical_file && (
                        <Button
                          size="small"
                          onClick={() => handleDownload(doc, 'canonical')}
                        >
                          Скачать каноническую форму
                        </Button>
                      )}
                      <Button
                        size="small"
                        onClick={() => handleReanalyze(doc)}
                        title="Повторно проанализировать"
                      >
                        🔄
                      </Button>
                    </>
                  )}
                  <Button
                    size="small"
                    variant="danger"
                    onClick={() => handleDelete(doc)}
                  >
                    Удалить
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
