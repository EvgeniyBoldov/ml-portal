import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '@/shared/ui/Toast';
import { adminApi, type MemoryScopeAdminItem, type SemanticMemoryAdminDetail, type ShadowMemoryCandidate } from '@/shared/api/admin';
import MemoryDetail from './MemoryDetail';

const scope: MemoryScopeAdminItem = { id: 'scope-1', key: 'team.ops', name: 'Эксплуатация', scope_type: 'team',
  aliases: [], is_all: false, project_id: null, lifecycle_status: 'active', retention_days: 30 };
const candidate: ShadowMemoryCandidate = {
  id: 'candidate-1', snapshot_id: 'snapshot-1', document_title: 'Регламент', visibility_tenant_id: null,
  candidate_type: 'rule', subject: 'Резервное копирование', normalized_subject: 'backup',
  content: { statement: 'Создайте копию', effect: 'require' }, content_text: 'Создайте копию',
  content_valid: true, content_error: null, aliases: [], related_entities: [], related_project_keys: [],
  evidence_section_ids: ['s1'], scope_candidate: 'unknown', resolution_status: 'needs_review', extraction_confidence: 0.8,
  project_ids: [], scope_ids: [], scope_keys: [], mentioned_scope_keys: [], unmatched_scope_names: [], scope_rationale: null,
  conflict_ids: [], scope_proposals: [], related_terms: [], approval_blockers: [], glossary_term_ids: [],
};
const published: SemanticMemoryAdminDetail = {
  id: 'item-1', subject: candidate.subject, item_type: 'rule', scope: 'scoped', scope_keys: ['team.ops'], project_id: null,
  content: candidate.content, content_text: candidate.content_text, confidence: 0.8, state: 'active',
  source_count: 1, claim_count: 1, last_verified_at: '2026-10-02T10:00:00Z', updated_at: '2026-10-02T10:00:00Z',
  applicability: {}, visibility: {}, aliases: [], related_project_keys: [],
  related_entities: [{ type: 'glossary_term', id: 'term-1', name: 'Сеть' }],
  sources: [{ document_id: 'doc-1', document_title: 'Регламент', canonical_checksum: 'checksum', section_id: 's1',
    label: 'Основание', start_offset: 0, end_offset: 100 }],
  claims: [{ id: 'claim-1', approved_candidate_id: candidate.id, document_id: 'doc-1', canonical_checksum: 'checksum',
    scope: 'scoped', scope_keys: ['team.ops'], item_type: 'rule', project_id: null, normalized_subject: 'backup',
    confidence: 0.8, state: 'active', evidence_section_ids: ['s1'], content: candidate.content, applicability: {},
    visibility_tenant_id: null, updated_at: '2026-10-02T10:00:00Z' }],
  relations: [], evaluations: [],
};
function card(props: { candidate?: ShadowMemoryCandidate; published?: SemanticMemoryAdminDetail }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter initialEntries={['/card']}>
    <Routes><Route path="/card" element={<MemoryDetail {...props} />} />
      <Route path="/admin/memory" element={<p>Список памяти</p>} /></Routes>
  </MemoryRouter></ToastProvider></QueryClientProvider>);
}
beforeEach(() => {
  vi.spyOn(adminApi, 'getMemoryScopes').mockResolvedValue([scope]);
  vi.spyOn(adminApi, 'getMemoryTermCatalog').mockResolvedValue([{ id: 'term-1', canonical_term: 'Сеть', definition: 'Корпоративная сеть', aliases: [] }]);
  vi.spyOn(adminApi, 'getShadowCandidateEvidence').mockResolvedValue({ document_title: 'Регламент',
    sections: [{ id: 's1', label: 'Основание', text: 'Исходный текст о копировании' }] });
  vi.spyOn(adminApi, 'updateShadowCandidateTags').mockResolvedValue(candidate);
  vi.spyOn(adminApi, 'approveShadowMemoryCandidate').mockResolvedValue({ ...candidate, resolution_status: 'resolved' });
  vi.spyOn(adminApi, 'rejectShadowMemoryCandidate').mockResolvedValue({ ...candidate, resolution_status: 'rejected' });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Общая карточка памяти', () => {
  it('показывает связи утверждённой памяти и отдельно загружает основания', async () => {
    card({ published });
    expect(screen.queryByRole('button', { name: 'Утвердить' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Утверждённая память' })).toHaveAttribute('href', '/admin/memory?tab=memory');
    expect(adminApi.getShadowCandidateEvidence).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    expect(await screen.findByText('Эксплуатация')).toBeInTheDocument();
    expect(screen.getByText('Сеть')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Происхождение' }));
    expect(await screen.findByText('Исходный текст о копировании')).toBeInTheDocument();
    expect(screen.queryByText('Эксплуатация')).not.toBeInTheDocument();
    expect(screen.queryByText('Сеть')).not.toBeInTheDocument();
  });
  it('разрешает утверждение после выбора связи и сохраняет теги перед решением', async () => {
    card({ candidate });
    const approve = screen.getByRole('button', { name: 'Утвердить' });
    expect(approve).toBeDisabled();
    expect(screen.getByRole('link', { name: 'На проверке' })).toHaveAttribute('href', '/admin/memory?tab=review');
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    const teams = screen.getByRole('combobox', { name: 'Команды' });
    await waitFor(() => expect(teams).not.toBeDisabled());
    fireEvent.focus(teams);
    fireEvent.click(await screen.findByRole('option', { name: 'Эксплуатация' }));
    expect(approve).not.toBeDisabled();
    fireEvent.click(approve);
    expect(await screen.findByText('Список памяти')).toBeInTheDocument();
    expect(adminApi.updateShadowCandidateTags).toHaveBeenCalledWith(candidate.id, expect.objectContaining({ scope_ids: ['scope-1'] }));
    expect(adminApi.updateShadowCandidateTags).toHaveBeenCalledBefore(vi.mocked(adminApi.approveShadowMemoryCandidate));
  });
  it('отклоняет кандидата с обязательной причиной', async () => {
    card({ candidate });
    fireEvent.click(screen.getByRole('button', { name: 'Отклонить' }));
    const reason = screen.getByLabelText('Причина отклонения *');
    const buttons = screen.getAllByRole('button', { name: 'Отклонить' });
    expect(buttons[buttons.length - 1]).toBeDisabled();
    fireEvent.change(reason, { target: { value: 'В документе другое условие' } });
    fireEvent.click(buttons[buttons.length - 1]);
    expect(await screen.findByText('Список памяти')).toBeInTheDocument();
    expect(adminApi.rejectShadowMemoryCandidate).toHaveBeenCalledWith(candidate.id, 'В документе другое условие');
    expect(adminApi.updateShadowCandidateTags).not.toHaveBeenCalled();
  });
});
