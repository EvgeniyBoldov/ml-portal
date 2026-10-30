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

import { capabilityReasonCopy } from '../capabilityReasonCopy';
import { TemplateSchemaViewer } from './TemplateSchemaViewer';
import { formatTemplateSchemaCounts, getTemplateSchemaCounts } from './templateSchemaPresentation';
import {
  formatTemplateFormat,
  formatTemplateStatus,
  getTemplateStageDescription,
  parseTemplateDescription,
} from './templateStatusPresentation';

function TemplateDescription({ text }: { text: string }) {
  const parsed = parseTemplateDescription(text);
  if (!parsed.sections.length) {
    return <p className={styles.descriptionFallback}>{parsed.fallback}</p>;
  }

  return (
    <div className={styles.descriptionContent}>
      {parsed.introduction && <p className={styles.descriptionIntro}>{parsed.introduction}</p>}
      {parsed.sections.map((section, index) => (
        <section key={`${section.heading}-${index}`} className={styles.descriptionPart}>
          <h5>{section.heading}</h5>
          <ul>
            {section.items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{item}</li>)}
          </ul>
        </section>
      ))}
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
        if (metrics.format) items.push({ label: 'Формат', value: formatTemplateFormat(metrics.format) ?? String(metrics.format) });
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
        break;
      case 'description':
        if (metrics.title) items.push({ label: 'Заголовок', value: String(metrics.title) });
        if (metrics.version) items.push({ label: 'Версия', value: String(metrics.version) });
        break;
      case 'approval':
        items.push({ label: 'Статус', value: formatTemplateStatus(metrics.approval_state ?? graph.runtime_status ?? graph.status ?? 'pending') });
        if (metrics.approved_by ?? graph.approved_by) {
          const approvedBy = String(metrics.approved_by ?? graph.approved_by);
          const approvedByName = graph.approved_by_name?.trim();
          items.push({ label: 'Утвердил', value: approvedByName || 'Пользователь недоступен', title: approvedBy });
        }
        break;
      case 'vectorization':
        if (metrics.chunks_prepared !== undefined) items.push({ label: 'Подготовлено векторов', value: Number(metrics.chunks_prepared) });
        if (metrics.chunk_count !== undefined && Number(metrics.chunk_count) !== Number(metrics.chunks_prepared)) {
          items.push({ label: 'Чанков для модели', value: Number(metrics.chunk_count) });
        }
        if (metrics.model_alias) items.push({ label: 'Модель', value: String(metrics.model_alias) });
        break;
      case 'indexing':
        if (metrics.indexed_count !== undefined) items.push({ label: 'Записей в индексе', value: Number(metrics.indexed_count) });
        if (metrics.chunk_count !== undefined && Number(metrics.chunk_count) !== Number(metrics.indexed_count)) {
          items.push({ label: 'Обработано чанков', value: Number(metrics.chunk_count) });
        }
        break;
      case 'ready':
        if (graph.template_version) items.push({ label: 'Версия', value: graph.template_version });
        items.push({ label: 'Статус', value: formatTemplateStatus(graph.runtime_status ?? graph.status ?? 'uploaded') });
        const templateFormat = formatTemplateFormat(graph.template_schema?.format);
        if (templateFormat) items.push({ label: 'Формат', value: templateFormat });
        items.push({ label: 'Структура', value: formatTemplateSchemaCounts(getTemplateSchemaCounts(graph.template_schema)).join(', ') || 'Поля не определены' });
        if (graph.approved_by) {
          items.push({ label: 'Утвердил', value: graph.approved_by_name?.trim() || 'Пользователь недоступен', title: String(graph.approved_by) });
        }
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
      finished_at: selectedNode.finished_at || (selectedNode.key === 'approval'
        ? (typeof selectedStage?.metrics?.approved_at === 'string' ? selectedStage.metrics.approved_at : graph.approved_at)
        : undefined),
    };
  }, [graph.approved_at, selectedNode, selectedStage?.metrics]);

  const selectedDescription = selectedNode?.key === 'description'
    ? String(selectedStage?.metrics?.description_text ?? graph.description ?? '')
    : '';

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
          <Alert variant="warning" title="Только просмотр" description="Изменять содержимое могут администраторы и редакторы этой рабочей группы." />
        )}
        <div className={styles.pipelineSection}>
          <StatusFlowView
            model={flowModel}
            selection={selection}
            onSelect={setSelection}
            compact
          />
        </div>
        <div className={styles.detailsSection}>
          <StatusFlowDetails
            node={selectedNodeForDetails}
            infoItems={infoItems}
            processingText="Этап выполняется..."
            compact
            stageDescription={selectedNode ? getTemplateStageDescription(selectedNode.key) : undefined}
            longDescription={selectedDescription ? <TemplateDescription text={selectedDescription} /> : undefined}
            stageContent={selectedNode?.key === 'schema' && !awaitingApproval ? <TemplateSchemaViewer schema={graph.template_schema} /> : undefined}
          />
        </div>
        {awaitingApproval && (
          <div className={`${styles.detailsSection} ${styles.approvalSection}`}>
            <div className={styles.approvalHeading}>
              <h3>Проверьте шаблон перед согласованием</h3>
              <p>Поля и их типы используются при заполнении шаблона.</p>
            </div>
            <section className={styles.schemaSection} aria-label="Структура шаблона">
              <h4>Структура шаблона</h4>
              <TemplateSchemaViewer schema={graph.template_schema} />
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
