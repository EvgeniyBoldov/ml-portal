import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '@/shared/ui/Toast';
import { adminApi, type MemoryScopeAdminItem, type SemanticMemoryAdminDetail, type ShadowMemoryCandidate } from '@/shared/api/admin';
import MemoryDetail from './MemoryDetail';
import { qk } from '@/shared/api/keys';

const scope: MemoryScopeAdminItem = { id: 'scope-1', key: 'team.ops', name: 'Эксплуатация', scope_type: 'team',
  aliases: [], is_all: false, project_type: null, project_id: null, lifecycle_status: 'active', retention_days: 30 };
const candidate: ShadowMemoryCandidate = {
  id: 'candidate-1', snapshot_id: 'snapshot-1', document_title: 'Регламент', visibility_tenant_id: null,
  candidate_type: 'rule', subject: 'Резервное копирование', normalized_subject: 'backup',
  content: { statement: 'Создайте копию', effect: 'require', conditions: ['Перед изменениями'] }, content_text: 'Создайте копию',
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
function CandidateCard({ candidate: initialCandidate }: { candidate: ShadowMemoryCandidate }) {
  const { data } = useQuery({ queryKey: qk.admin.memory.candidate(initialCandidate.id),
    queryFn: () => Promise.resolve(initialCandidate), initialData: initialCandidate, enabled: false });
  return <MemoryDetail candidate={data} />;
}
function PublishedCard({ published: initialPublished }: { published: SemanticMemoryAdminDetail }) {
  const { data } = useQuery({ queryKey: qk.admin.memory.item(initialPublished.id),
    queryFn: () => Promise.resolve(initialPublished), initialData: initialPublished, enabled: false });
  return <MemoryDetail published={data} />;
}
function card(props: { candidate?: ShadowMemoryCandidate; published?: SemanticMemoryAdminDetail }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter initialEntries={['/card']}>
    <Routes><Route path="/card" element={props.candidate ? <CandidateCard candidate={props.candidate} /> : <PublishedCard published={props.published!} />} />
      <Route path="/admin/memory" element={<p>Список памяти</p>} /></Routes>
  </MemoryRouter></ToastProvider></QueryClientProvider>);
}
beforeEach(() => {
  vi.spyOn(adminApi, 'getMemoryScopes').mockResolvedValue([scope]);
  vi.spyOn(adminApi, 'getMemoryTermCatalog').mockResolvedValue([{ id: 'term-1', canonical_term: 'Сеть', definition: 'Корпоративная сеть', aliases: [] }]);
  vi.spyOn(adminApi, 'getShadowCandidateEvidence').mockResolvedValue({ document_title: 'Регламент',
    sections: [{ id: 's1', label: 'Основание', text: 'Исходный текст о копировании' }] });
  vi.spyOn(adminApi, 'updateShadowCandidateTags').mockResolvedValue(candidate);
  vi.spyOn(adminApi, 'approveShadowMemoryCandidate').mockImplementation(async (_id, body) => ({ ...candidate,
    resolution_status: 'resolved', published_item_id: published.id, scope_ids: body?.tags?.scope_ids ?? [],
    scope_candidate: body?.tags?.scope_ids.length ? 'scoped' : 'global', glossary_term_ids: body?.tags?.glossary_term_ids ?? [] }));
  vi.spyOn(adminApi, 'updateSemanticMemoryLinks').mockResolvedValue(published);
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
    expect(screen.getByRole('combobox', { name: 'Команды' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: 'Термины' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Происхождение' }));
    expect(await screen.findByText('Исходный текст о копировании')).toBeInTheDocument();
    expect(screen.queryByText('Эксплуатация')).not.toBeInTheDocument();
    expect(screen.queryByText('Сеть')).not.toBeInTheDocument();
  });
  it('разрешает утверждение после выбора связи и передаёт поля вместе с решением', async () => {
    card({ candidate });
    const approve = screen.getByRole('button', { name: 'Утвердить' });
    expect(approve).toBeDisabled();
    expect(screen.getByRole('link', { name: 'На проверке' })).toHaveAttribute('href', '/admin/memory?tab=review');
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    const teams = screen.getByRole('combobox', { name: 'Команды' });
    await waitFor(() => expect(teams).not.toBeDisabled());
    fireEvent.focus(teams);
    fireEvent.click(await screen.findByRole('option', { name: 'Эксплуатация' }));
    await waitFor(() => expect(approve).not.toBeDisabled());
    fireEvent.click(approve);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Утвердить' })).not.toBeInTheDocument());
    expect(adminApi.approveShadowMemoryCandidate).toHaveBeenCalledWith(candidate.id, { tags: expect.objectContaining({ scope_ids: ['scope-1'] }) });
    expect(adminApi.updateShadowCandidateTags).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox', { name: 'Команды' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Редактировать' })).toBeInTheDocument();
  });
  it('переключает один блок содержания между разделами и JSON через хедер', async () => {
    card({ published });
    fireEvent.click(screen.getByRole('button', { name: 'Содержимое' }));
    expect(screen.getAllByRole('heading', { name: 'Содержание памяти' })).toHaveLength(1);
    expect(screen.getByText('Формулировка')).toBeInTheDocument();
    expect(screen.getByText('Создайте копию')).toBeInTheDocument();
    const toggle = screen.getByRole('checkbox', { name: 'JSON' });
    const header = screen.getByRole('heading', { name: 'Содержание памяти' }).parentElement;
    expect(header).toContainElement(toggle);
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(screen.queryByText('Формулировка')).not.toBeInTheDocument();
    expect(document.querySelector('pre')?.textContent).toBe(JSON.stringify(published.content, null, 2));
    fireEvent.click(toggle);
    expect(screen.getByText('Формулировка')).toBeInTheDocument();
  });
  it('утверждает внепроектное знание с пустыми связями без чекбокса', async () => {
    card({ candidate });
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    expect(screen.queryByRole('checkbox', { name: 'Подтвердить внепроектное знание без адресата' })).not.toBeInTheDocument();
    const approve = screen.getByRole('button', { name: 'Утвердить' });
    await waitFor(() => expect(approve).not.toBeDisabled());
    fireEvent.click(approve);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Утвердить' })).not.toBeInTheDocument());
    expect(adminApi.approveShadowMemoryCandidate).toHaveBeenCalledWith(candidate.id, { tags: { scope_ids: [], glossary_term_ids: [], reason: '' } });
  });
  it('показывает условия в применимости, связи один раз и без кнопки к списку', async () => {
    card({ published });
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    const applicabilityBlock = screen.getByRole('heading', { name: 'Применимость' }).parentElement!.parentElement!;
    const linksBlock = screen.getByRole('heading', { name: 'Связи' }).parentElement!.parentElement!;
    expect(within(applicabilityBlock).getByText('Перед изменениями')).toBeInTheDocument();
    expect(within(applicabilityBlock).queryByText('Команды')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Дополнительная применимость' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'К списку' })).not.toBeInTheDocument();
    await waitFor(() => expect(within(linksBlock).getByText('Сеть')).toBeInTheDocument());
    expect(screen.getAllByText('Сеть')).toHaveLength(1);
    expect(within(linksBlock).getByRole('combobox', { name: 'Команды' })).toBeDisabled();
  });
  it('разблокирует поля связей кнопкой хедера страницы и сохраняет утверждённую память', async () => {
    vi.mocked(adminApi.updateSemanticMemoryLinks).mockResolvedValue({ ...published, related_entities: [] });
    card({ published });
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    const edit = screen.getByRole('button', { name: 'Редактировать' });
    await waitFor(() => expect(edit).not.toBeDisabled());
    expect(screen.getByRole('heading', { name: 'Связи' }).parentElement).not.toContainElement(edit);
    expect(screen.getByRole('heading', { name: published.subject }).closest('header')).toContainElement(edit);
    fireEvent.click(edit);
    const terms = screen.getByRole('combobox', { name: 'Термины' });
    expect(terms).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Убрать Сеть' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(adminApi.updateSemanticMemoryLinks).toHaveBeenCalledWith(published.id, expect.objectContaining({ scope_ids: ['scope-1'], glossary_term_ids: [] })));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Термины' })).toBeDisabled());
    expect(screen.queryByText('Сеть')).not.toBeInTheDocument();
    expect(screen.queryByText('Список памяти')).not.toBeInTheDocument();
  });
  it('сохраняет введённые связи при ошибке сохранения', async () => {
    vi.mocked(adminApi.updateSemanticMemoryLinks).mockRejectedValue(new Error('Связи не сохранены'));
    card({ published });
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    const edit = screen.getByRole('button', { name: 'Редактировать' });
    await waitFor(() => expect(edit).not.toBeDisabled());
    fireEvent.click(edit);
    fireEvent.click(screen.getByRole('button', { name: 'Убрать Сеть' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Связи не сохранены')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Термины' })).not.toBeDisabled();
    expect(screen.queryByText('Сеть')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сохранить' })).not.toBeDisabled();
  });
  it('показывает условия из применимости, если их нет в содержании', async () => {
    card({ published: { ...published, content: { statement: 'Создайте копию', effect: 'require' },
      applicability: { conditions: ['После согласования'] } } });
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    expect(screen.getByText('После согласования')).toBeInTheDocument();
  });
  it('отмена возвращает сохранённые связи и закрывает редактирование', async () => {
    card({ published });
    fireEvent.click(screen.getByRole('button', { name: 'Связи и применимость' }));
    const edit = screen.getByRole('button', { name: 'Редактировать' });
    await waitFor(() => expect(edit).not.toBeDisabled());
    fireEvent.click(edit);
    fireEvent.click(screen.getByRole('button', { name: 'Убрать Сеть' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(screen.getByText('Сеть')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Термины' })).toBeDisabled();
    expect(adminApi.updateSemanticMemoryLinks).not.toHaveBeenCalled();
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
