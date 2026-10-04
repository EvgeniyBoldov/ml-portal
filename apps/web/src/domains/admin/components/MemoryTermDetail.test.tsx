import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '@/shared/ui/Toast';
import { adminApi, type AdminGlossaryTerm, type ShadowMemoryCandidate } from '@/shared/api/admin';
import MemoryItemPage from '../pages/MemoryItemPage';
import MemoryTermDetail from './MemoryTermDetail';
import { DataTable } from '@/shared/ui';
import { reviewColumns } from './MemoryReviewTable';

const candidate: ShadowMemoryCandidate = { id: 'candidate-term', snapshot_id: 's1', document_title: 'Регламент',
  document_access_scope: 'collection', visibility_tenant_id: null, candidate_type: 'term', subject: 'Окно работ', normalized_subject: 'окно работ',
  content: { definition: 'Период согласованных работ' }, content_text: '{"definition":"Период согласованных работ"}',
  content_valid: true, content_error: null, aliases: ['ОР'], related_entities: [], glossary_term_ids: [], related_project_keys: [],
  evidence_section_ids: ['section1'], scope_candidate: null, resolution_status: 'needs_review', extraction_confidence: 0.9,
  project_ids: [], scope_ids: [], scope_keys: [], mentioned_scope_keys: [], unmatched_scope_names: [], scope_rationale: null,
  conflict_ids: [], scope_proposals: [], related_terms: [], approval_blockers: [] };
const term: AdminGlossaryTerm = { id: 'term1', canonical_term: candidate.subject, normalized_term: candidate.normalized_subject,
  definition: 'Период согласованных работ', aliases: ['ОР'], is_active: true, approved_candidate_id: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' };

function page(element: React.ReactElement, path = '/card') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/card" element={element} /><Route path="/admin/memory/review/:candidateId" element={element} />
    <Route path="/admin/memory" element={<p>Очередь проверки</p>} />
  </Routes></MemoryRouter></ToastProvider></QueryClientProvider>);
}
beforeEach(() => {
  vi.spyOn(adminApi, 'getGlossary').mockResolvedValue([]);
  vi.spyOn(adminApi, 'getShadowMemoryCandidate').mockResolvedValue(candidate);
  vi.spyOn(adminApi, 'approveShadowMemoryCandidate').mockResolvedValue({ ...candidate, resolution_status: 'resolved' });
  vi.spyOn(adminApi, 'updateShadowCandidateTags');
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Карточка термина и очередь проверки', () => {
  it('открывает термин на проверке отдельной страницей без team/project-применимости', async () => {
    page(<MemoryItemPage />, '/admin/memory/review/candidate-term');
    const approve = await screen.findByRole('button', { name: 'Утвердить термин' });
    await waitFor(() => expect(approve).not.toBeDisabled());
    expect(screen.getByText('Период согласованных работ')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Связи и применимость' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Содержимое' })).not.toBeInTheDocument();
    fireEvent.click(approve);
    expect(await screen.findByText('Очередь проверки')).toBeInTheDocument();
    expect(adminApi.approveShadowMemoryCandidate).toHaveBeenCalledWith(candidate.id, {});
    expect(adminApi.updateShadowCandidateTags).not.toHaveBeenCalled();
  });
  it('показывает утверждённый термин без сохранившегося источника', () => {
    page(<MemoryTermDetail term={term} />);
    expect(screen.getByText('Период согласованных работ')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Утвердить термин' })).not.toBeInTheDocument();
  });
  it('показывает термин в общей таблице на проверке готовым к утверждению', () => {
    render(<MemoryRouter><DataTable columns={reviewColumns} data={[candidate]} keyField="id" /></MemoryRouter>);
    expect(screen.getByText('Окно работ')).toBeInTheDocument();
    expect(screen.getByText('Термин')).toBeInTheDocument();
    expect(screen.getByText('Период согласованных работ')).toBeInTheDocument();
    expect(screen.getByText('Готов к утверждению')).toBeInTheDocument();
  });
});
