import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import Modal from '@shared/ui/Modal';
import Button from '@shared/ui/Button';
import Alert from '@shared/ui/Alert';
import { useToast } from '@shared/ui/Toast';
import { openSSE, type SSEMessage } from '@shared/lib/sse';
import { collectionsApi, type Collection, type CollectionTemplate } from '@shared/api/collections';
import { ApiError } from '@shared/api/errors';
import { qk } from '@shared/api/keys';
import {
  StatusFlowDetails,
  StatusFlowView,
  adaptTemplateStatusGraphToFlowModel,
  buildTemplateFallbackGraph,
  useStatusFlowSelection,
  type FlowNode,
  type FlowDetailItem,
} from '@shared/components/statusFlow';
import type { TemplateStatusGraphModel } from '@shared/components/statusFlow/templateFlowAdapter';
import styles from './TemplateStatusModal.module.css';

import { summarizeTemplateSchema } from '@shared/lib/templateSchemaSummary';
import { capabilityReasonCopy } from '../capabilityReasonCopy';

type SchemaField = Record<string, unknown> & { key: string };

function getSchemaFields(schema: Record<string, unknown> | null | undefined): SchemaField[] {
  if (!schema) return [];
  if (Array.isArray(schema.fields)) {
    return schema.fields.flatMap((field) => {
      if (!field || typeof field !== 'object') return [];
      const value = field as Record<string, unknown>;
      const key = String(value.key ?? value.name ?? value.label ?? '').trim();
      return key ? [{ ...value, key }] : [];
    });
  }
  if (schema.properties && typeof schema.properties === 'object') {
    const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : []);
    return Object.entries(schema.properties as Record<string, unknown>).flatMap(([key, value]) => {
      if (!value || typeof value !== 'object') return [];
      return [{ key, ...(value as Record<string, unknown>), required: required.has(key) }];
    });
  }
  return [];
}

function SchemaPreview({ schema }: { schema: Record<string, unknown> | null | undefined }) {
  const fields = getSchemaFields(schema);
  if (fields.length === 0) {
    return <p className={styles.schemaEmpty}>Описание полей для этого шаблона пока не сформировано.</p>;
  }

  return (
    <div className={styles.schemaFields}>
      {fields.map((field, index) => {
        const label = String(field.label ?? field.title ?? field.key);
        const kind = String(field.kind ?? (Array.isArray(field.columns) ? 'table' : 'field'));
        const columns = Array.isArray(field.columns) ? field.columns : [];
        const knownKeys = new Set([
          'key', 'name', 'label', 'title', 'kind', 'type', 'description', 'required',
          'example', 'enum', 'columns', 'orientation', 'min_rows', 'max_rows',
        ]);
        const technicalAttributes = Object.entries(field).filter(([key]) => !knownKeys.has(key));
        const rowRange = field.min_rows !== undefined || field.max_rows !== undefined
          ? `${field.min_rows ?? 0}–${field.max_rows ?? 'без ограничения'} строк`
          : null;

        return (
          <details className={styles.schemaField} key={`${field.key}-${index}`}>
            <summary className={styles.schemaFieldSummary}>
              <span className={styles.schemaFieldName}>{label}</span>
              <span className={`${styles.schemaBadge} ${kind === 'table' ? styles.tableBadge : ''}`}>
                {kind === 'table' ? 'Таблица' : String(field.type ?? 'Поле')}
              </span>
              {field.required === true && <span className={`${styles.schemaBadge} ${styles.requiredBadge}`}>Обязательное</span>}
              {kind === 'table' && Boolean(field.orientation) && (
                <span className={styles.schemaBadge}>
                  {field.orientation === 'horizontal' ? 'По столбцам' : 'По строкам'}
                </span>
              )}
              {rowRange && <span className={styles.schemaFieldMeta}>{rowRange}</span>}
              {columns.length > 0 && <span className={styles.schemaFieldMeta}>{columns.length} столбц.</span>}
              <span className={styles.schemaChevron} aria-hidden="true">⌄</span>
            </summary>
            <div className={styles.schemaFieldBody}>
              <div className={styles.schemaKey}>{field.key}</div>
              {typeof field.description === 'string' && field.description.trim() && (
                <p className={styles.schemaDescription}>{field.description}</p>
              )}
              {columns.length > 0 && (
                <div className={styles.schemaColumns}>
                  {columns.map((column, columnIndex) => {
                    if (!column || typeof column !== 'object') return null;
                    const item = column as Record<string, unknown>;
                    const columnLabel = String(item.label ?? item.key ?? `Столбец ${columnIndex + 1}`);
                    return (
                      <span className={styles.schemaColumn} key={`${columnLabel}-${columnIndex}`}>
                        {columnLabel}{item.type ? <small>{String(item.type)}</small> : null}
                      </span>
                    );
                  })}
                </div>
              )}
              {(field.example !== undefined || Array.isArray(field.enum)) && (
                <div className={styles.schemaExamples}>
                  {field.example !== undefined && <span>Пример: {String(field.example)}</span>}
                  {Array.isArray(field.enum) && <span>Варианты: {field.enum.map(String).join(', ')}</span>}
                </div>
              )}
              {technicalAttributes.length > 0 && (
                <details className={styles.technicalDetails}>
                  <summary>Технические атрибуты</summary>
                  <dl>
                    {technicalAttributes.map(([key, value]) => (
                      <div key={key}>
                        <dt>{key}</dt>
                        <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

interface TemplateStatusModalProps {
  collectionId: string;
  tenantId?: string;
  collection: Collection;
  permissionDenied?: boolean;
  onPermissionDenied: (reason?: 'forbidden' | 'unavailable') => void | Promise<Collection | null>;
  row: CollectionTemplate;
  onClose: () => void;
}

export function TemplateStatusModal({ collectionId, tenantId, collection, permissionDenied = false, onPermissionDenied, row, onClose }: TemplateStatusModalProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const statusQueryKey = useMemo(() => qk.collections.templateStatus(collectionId, row.id, tenantId), [collectionId, row.id, tenantId]);
  const [descriptionDraft, setDescriptionDraft] = useState(String(row.description ?? ''));
  const [savedDescription, setSavedDescription] = useState(String(row.description ?? ''));
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [permissionError, setPermissionError] = useState(false);
  const [permissionDeniedLocally, setPermissionDeniedLocally] = useState(false);
  const canEditContent = !permissionDenied && !permissionDeniedLocally && collection.capabilities?.can_edit_content === true;
  const canEditTemplate = !permissionDenied && !permissionDeniedLocally && collection.capabilities?.edit_templates === true;
  const canApproveTemplate = !permissionDenied && !permissionDeniedLocally && collection.capabilities?.approve_templates === true;
  const editReason = capabilityReasonCopy(collection.capability_reasons?.edit_templates, 'Редактирование шаблона временно недоступно.');
  const approveReason = capabilityReasonCopy(collection.capability_reasons?.approve_templates, 'Согласование шаблона временно недоступно.');

  const { data: statusGraph } = useQuery<TemplateStatusGraphModel>({
    queryKey: statusQueryKey,
    queryFn: async () => {
      const data = await collectionsApi.getTemplateStatusGraph(collectionId, row.id, tenantId);
      return data as unknown as TemplateStatusGraphModel;
    },
    placeholderData: () => buildTemplateFallbackGraph(row),
    staleTime: 0,
  });
  const graph = statusGraph ?? buildTemplateFallbackGraph(row);

  useEffect(() => {
    const description = String(row.description ?? '');
    setDescriptionDraft(description);
    setSavedDescription(description);
  }, [row]);

  useEffect(() => {
    setPermissionError(false);
    setPermissionDeniedLocally(false);
  }, [collectionId, tenantId, row.id]);

  useEffect(() => {
    if (!permissionDenied) {
      setPermissionDeniedLocally(false);
      setPermissionError(false);
    }
  }, [permissionDenied]);

  useEffect(() => {
    let disposed = false;
    const client = openSSE(
      collectionsApi.getTemplateStatusEventsUrl(collectionId, row.id, tenantId),
      (events: SSEMessage[]) => {
        for (const event of events) {
          if (event.type !== 'rag.snapshot') continue;
          const data = event.data as Record<string, unknown>;
          const next = (data.graph ?? data) as TemplateStatusGraphModel;
          if (!disposed && next) {
            queryClient.setQueryData(statusQueryKey, next);
          }
        }
      },
    );

    return () => {
      disposed = true;
      client.disconnect();
    };
  }, [collectionId, queryClient, row.id, statusQueryKey, tenantId]);

  const flowModel = useMemo(() => adaptTemplateStatusGraphToFlowModel(graph), [graph]);
  const { selection, setSelection } = useStatusFlowSelection(flowModel);

  const selectedNode = useMemo(() => {
    if (!selection.nodeKey) return null;
    return flowModel.pipeline.find((item) => item.key === selection.nodeKey) ?? null;
  }, [flowModel, selection.nodeKey]);

  const selectedStage = useMemo(
    () => graph.stages?.find((stage) => stage.key === selectedNode?.key) ?? null,
    [graph.stages, selectedNode?.key],
  );

  const infoItems = useMemo<FlowDetailItem[]>(() => {
    if (!selectedNode || selectedNode.error) return [];
    const metrics = (selectedStage?.metrics ?? {}) as Record<string, unknown>;
    const items: FlowDetailItem[] = [];
    switch (selectedNode.key) {
      case 'uploaded':
        if (metrics.filename) items.push({ label: 'Файл', value: String(metrics.filename) });
        if (metrics.format) items.push({ label: 'Формат', value: String(metrics.format) });
        if (metrics.file_size) {
          const bytes = Number(metrics.file_size);
          const size = bytes >= 1024 * 1024
            ? `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
            : `${Math.max(1, Math.round(bytes / 1024))} КБ`;
          items.push({ label: 'Размер', value: size });
        }
        if (Array.isArray(metrics.sheet_names) && metrics.sheet_names.length > 0) {
          items.push({ label: 'Листы', value: metrics.sheet_names as string[] });
        }
        break;
      case 'schema':
        if (metrics.title) items.push({ label: 'Заголовок', value: String(metrics.title) });
        if (metrics.version) items.push({ label: 'Версия', value: String(metrics.version) });
        if (metrics.format) items.push({ label: 'Формат', value: String(metrics.format) });
        if (Array.isArray(metrics.sheet_names) && metrics.sheet_names.length > 0) {
          items.push({ label: 'Листы', value: metrics.sheet_names as string[] });
        }
        break;
      case 'description':
        if (metrics.title) items.push({ label: 'Заголовок', value: String(metrics.title) });
        if (metrics.version) items.push({ label: 'Версия', value: String(metrics.version) });
        items.push({ label: 'Описание', value: String(metrics.description_text ?? graph.description ?? '—') });
        break;
      case 'approval':
        items.push({ label: 'Статус', value: String(metrics.approval_state ?? 'pending') });
        if (metrics.approved_by ?? graph.approved_by) {
          items.push({ label: 'Утвердил', value: String(metrics.approved_by ?? graph.approved_by) });
        }
        if (metrics.approved_at ?? graph.approved_at) {
          items.push({ label: 'Утверждено', value: String(metrics.approved_at ?? graph.approved_at) });
        }
        break;
      case 'vectorization':
        if (metrics.chunks_prepared !== undefined) items.push({ label: 'Подготовлено чанков', value: Number(metrics.chunks_prepared) });
        if (metrics.chunk_count !== undefined) items.push({ label: 'Чанков', value: Number(metrics.chunk_count) });
        break;
      case 'indexing':
        if (metrics.indexed_count !== undefined) items.push({ label: 'Проиндексировано', value: Number(metrics.indexed_count) });
        if (metrics.chunk_count !== undefined) items.push({ label: 'Чанков', value: Number(metrics.chunk_count) });
        break;
      case 'ready':
        if (graph.template_version) items.push({ label: 'Версия', value: graph.template_version });
        items.push({ label: 'Статус', value: String(graph.runtime_status ?? graph.status ?? 'uploaded') });
        items.push({ label: 'Схема', value: summarizeTemplateSchema(graph.template_schema) });
        if (graph.approved_by) items.push({ label: 'Утвердил', value: String(graph.approved_by) });
        break;
      default:
        break;
    }
    return items;
  }, [graph, selectedNode, selectedStage?.metrics]);

  const selectedNodeForDetails = useMemo<FlowNode | null>(() => {
    if (!selectedNode) return null;
    return {
      ...selectedNode,
      // Stage-specific, user-facing values are rendered through infoItems below.
      // Raw metrics can contain internal schema/debug fields, so keep them out of the default view.
      metrics: {},
    };
  }, [selectedNode]);

  const title = graph.title || row.title || 'Статус шаблона';
  const awaitingApproval = String(graph.runtime_status ?? graph.status ?? row.runtime_status ?? row.status ?? '').toLowerCase() === 'approval_required';
  const dirty = descriptionDraft !== savedDescription;
  const refreshPermissionState = async () => {
    setPermissionError(true);
    setPermissionDeniedLocally(true);
    try {
      await onPermissionDenied('forbidden');
    } catch {
      // Keep the local deny latch set when the fresh capability request fails.
    }
  };
  const saveDescription = async () => {
    if (!canEditContent || !canEditTemplate) return;
    setSaving(true);
    try {
      await collectionsApi.updateTemplate(collectionId, row.id, { description: descriptionDraft.trim() || null }, tenantId);
      setSavedDescription(descriptionDraft);
      await queryClient.invalidateQueries({ queryKey: qk.collections.templatesRoot(collectionId) });
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось сохранить описание', 'error');
      if (error instanceof ApiError && error.status === 403) {
        void refreshPermissionState();
      }
    } finally {
      setSaving(false);
    }
  };
  const approve = async () => {
    if (!canEditContent || !canApproveTemplate) return;
    setApproving(true);
    try {
      await collectionsApi.approveTemplate(collectionId, row.id, tenantId);
      await queryClient.invalidateQueries({ queryKey: qk.collections.templatesRoot(collectionId) });
      onClose();
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось согласовать шаблон', 'error');
      if (error instanceof ApiError && error.status === 403) {
        void refreshPermissionState();
      }
    } finally {
      setApproving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      size="fit"
      className={styles.modal}
      bodyClassName={styles.modalBody}
    >
      <div className={styles.container}>
        {permissionError && (
          <Alert variant="warning" title="Права изменились" description="Сервер отклонил изменение. Черновик сохранён; действия отключены до успешного подтверждения прав." />
        )}
        {!canEditContent && (
          <Alert variant="warning" title="Только просмотр" description="Изменять содержимое могут администраторы и редакторы этого тенанта." />
        )}
        <div className={styles.pipelineSection}>
          <StatusFlowView
            model={flowModel}
            selection={selection}
            onSelect={setSelection}
          />
        </div>
        <div className={styles.detailsSection}>
          <StatusFlowDetails
            node={selectedNodeForDetails}
            infoItems={infoItems}
            processingText="Этап выполняется..."
          />
        </div>
        {selectedNode?.key === 'schema' && !awaitingApproval && (
          <section className={`${styles.detailsSection} ${styles.schemaSection}`} aria-label="Поля шаблона">
            <div className={styles.schemaHeader}>
              <h4>Структура шаблона</h4>
              <span>{getSchemaFields(graph.template_schema).length}</span>
            </div>
            <SchemaPreview schema={graph.template_schema} />
          </section>
        )}
        {awaitingApproval && (
          <div className={`${styles.detailsSection} ${styles.approvalSection}`}>
            <div className={styles.approvalHeading}>
              <h3>Проверьте шаблон перед согласованием</h3>
              <p>Поля и их типы используются при заполнении шаблона.</p>
            </div>
            <section className={styles.schemaSection} aria-label="Поля шаблона">
              <div className={styles.schemaHeader}>
                <h4>Поля шаблона</h4>
                <span>{getSchemaFields(graph.template_schema).length}</span>
              </div>
              <SchemaPreview schema={graph.template_schema} />
            </section>
            <label className={styles.descriptionField}>
              Описание шаблона
              <textarea value={descriptionDraft} disabled={!canEditContent || !canEditTemplate} onChange={(event) => setDescriptionDraft(event.target.value)} rows={5} />
            </label>
            <div className={styles.approvalActions}>
              <Button variant="outline" onClick={onClose}>Отмена</Button>
              {(canEditContent || permissionDenied || permissionDeniedLocally) && <>
                <Button variant="outline" onClick={() => void saveDescription()} disabled={!canEditTemplate || saving || !dirty} title={!canEditTemplate ? editReason : undefined}>
                  {saving ? 'Сохранение…' : 'Сохранить описание'}
                </Button>
                <Button onClick={() => void approve()} disabled={!canApproveTemplate || approving || dirty} title={!canApproveTemplate ? approveReason : undefined}>
                  {approving ? 'Согласование…' : 'Согласовать шаблон'}
                </Button>
              </>}
            </div>
            {canEditContent && !canEditTemplate && <p role="status">{editReason}</p>}
            {canEditContent && !canApproveTemplate && <p role="status">{approveReason}</p>}
          </div>
        )}
      </div>
    </Modal>
  );
}

export default TemplateStatusModal;
