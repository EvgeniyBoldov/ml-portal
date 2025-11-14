import React, { useState, memo } from 'react';
import Badge from '@shared/ui/Badge';
import { MoreVerticalIcon } from '@shared/ui/Icon';
import TagBadge from '@shared/ui/TagBadge';
import { RagDocument } from '@shared/api/types/rag';
import { isPartial } from '@shared/lib/ragStatus';
import { StatusModal } from './StatusModal';
import StatusButton from './StatusButton';
import styles from './DocumentList.module.css';

interface DocumentListProps {
  documents: RagDocument[];
  onActionMenuOpen: (doc: RagDocument, element: HTMLElement) => void;
  isAdmin?: boolean;
}

// Memoized components for performance
const MemoizedTagBadge = memo(TagBadge);

export default function DocumentList({
  documents,
  onActionMenuOpen,
  isAdmin = false,
}: DocumentListProps) {
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<RagDocument | null>(null);

  const getScopeText = (scope: string) => {
    switch (scope) {
      case 'local':
        return 'Локальный';
      case 'global':
        return 'Глобальный';
      default:
        return scope;
    }
  };

  const formatDateTime = (dateString: string) => {
    try {
      if (!dateString) return '—';
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return '—';
      return date.toLocaleString('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch {
      return '—';
    }
  };

  const handleStatusClick = async (
    doc: RagDocument,
    event: React.MouseEvent
  ) => {
    event.stopPropagation();
    setSelectedDoc(doc);
    setStatusModalOpen(true);
  };

  const handleCloseStatusModal = async () => {
    setStatusModalOpen(false);
    setSelectedDoc(null);
  };

  return (
    <>
      <div className={styles.tableWrap}>
        <table className="table">
          <thead>
            <tr>
              <th>Имя</th>
              <th>Статус</th>
              <th>Скоуп</th>
              <th>Теги</th>
              <th>Дата создания</th>
              {isAdmin && <th>Тенант</th>}
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {documents.map(doc => (
              <tr key={doc.id}>
                <td className="muted">{doc.name || '—'}</td>
                <td>
                  <StatusButton
                    status={doc.agg_status || 'missing'}
                    onClick={e => handleStatusClick(doc, e)}
                    warning={isPartial(doc.emb_status || [])}
                  />
                </td>
                <td>
                  <Badge tone={doc.scope === 'global' ? 'success' : 'neutral'}>
                    {getScopeText(doc.scope)}
                  </Badge>
                </td>
                <td>
                  <div className="flex flex-wrap gap-1">
                    {doc.tags && doc.tags.length > 0 ? (
                      doc.tags.map(tag => (
                        <MemoizedTagBadge key={tag} tag={tag} />
                      ))
                    ) : (
                      <span className="text-gray-500 text-sm">—</span>
                    )}
                  </div>
                </td>
                <td className="muted">
                  {formatDateTime(doc.created_at || '')}
                </td>
                {isAdmin && <td className="muted">{doc.tenant_name || '—'}</td>}
                <td>
                  <button
                    className={`${styles.actionButton} icon`}
                    type="button"
                    aria-label="Действия"
                    onClick={e => onActionMenuOpen(doc, e.currentTarget)}
                    style={{
                      cursor: 'pointer',
                      padding: '8px',
                      borderRadius: '6px',
                      border: '1px solid var(--color-border)',
                      background: 'var(--color-background)',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    <MoreVerticalIcon />
                  </button>
                </td>
              </tr>
            ))}
            {documents.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 7 : 6} className="muted">
                  Нет записей
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Status Modal */}
      {statusModalOpen && selectedDoc && (
        <StatusModal docId={selectedDoc.id} onClose={handleCloseStatusModal} />
      )}
    </>
  );
}
