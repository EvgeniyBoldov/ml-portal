import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Badge, Button, Input, Modal, Select } from '@/shared/ui';
import { adminApi } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import styles from './LongMemoryTab.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function LongMemorySearchModal({ open, onClose }: Props) {
  const [scope, setScope] = useState('');
  const [query, setQuery] = useState('');
  const scopes = useQuery({ queryKey: qk.admin.memory.scopes(), queryFn: () => adminApi.getMemoryScopes(), enabled: open });
  const activeScopes = (scopes.data ?? []).filter((item) => item.lifecycle_status === 'active');
  const selectedScope = scope || activeScopes[0]?.key || '';
  const preview = useMutation({ mutationFn: () => adminApi.searchLongMemory({ scope_key: selectedScope, query: query.trim(), limit: 5 }) });

  const handleClose = () => {
    preview.reset();
    onClose();
  };

  return <Modal open={open} title="Тестовый поиск HippoRAG" onClose={handleClose} size="xl">
    <form className={styles.modalContent} onSubmit={(event) => { event.preventDefault(); if (selectedScope && query.trim()) preview.mutate(); }}>
      <p className={styles.modalHint}>Проверка retrieval по готовому графу выбранного scope. Будут показаны до пяти найденных фрагментов.</p>
      <label>Scope<Select value={selectedScope} options={activeScopes.map((item) => ({ value: item.key, label: `${item.name} (${item.key})` }))} disabled={!activeScopes.length} onChange={setScope} /></label>
      <label>Запрос<Input aria-label="Тестовый запрос LongMemory" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Что нужно найти?" /></label>
      {preview.isError && <p role="alert">Не удалось выполнить тестовый поиск.</p>}
      {preview.data && <div className={styles.results} aria-live="polite">
        {!preview.data.success ? <p role="alert">{preview.data.error || 'Поиск по этому scope завершился ошибкой.'}</p> : preview.data.hits.length === 0 ? <p>Подходящих фрагментов не найдено.</p> : <>
          <p className={styles.resultCount}>Найдено фрагментов: {preview.data.hits.length}</p>
          {preview.data.hits.map((hit, index) => <article className={styles.hit} key={`${hit.document_id ?? 'doc'}:${hit.start ?? index}:${index}`}>
            <div className={styles.hitHeader}><strong>{hit.title || hit.filename || hit.document_id || 'Документ'}</strong><Badge tone="neutral">score {hit.score.toFixed(3)}</Badge></div>
            <p>{hit.text}</p>
            {hit.start !== null && hit.end !== null && <small>Позиция в источнике: {hit.start}–{hit.end}</small>}
          </article>)}
        </>}
      </div>}
      <div className={styles.modalActions}>
        <Button type="button" variant="outline" onClick={handleClose}>Закрыть</Button>
        <Button type="submit" disabled={!selectedScope || !query.trim() || preview.isPending}>{preview.isPending ? 'Ищем…' : 'Искать'}</Button>
      </div>
    </form>
  </Modal>;
}
