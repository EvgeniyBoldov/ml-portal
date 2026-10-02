import { useQueries } from '@tanstack/react-query';
import { Button } from '@/shared/ui';
import { adminApi } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import styles from './MemoryReviewDialog.module.css';

export default function MemoryEvidence({ candidateIds, enabled }: { candidateIds: string[]; enabled: boolean }) {
  const ids = [...new Set(candidateIds)];
  const results = useQueries({ queries: ids.map((id) => ({
    queryKey: qk.admin.memory.candidateEvidence(id),
    queryFn: () => adminApi.getShadowCandidateEvidence(id),
    enabled, retry: false,
  })) });
  if (!ids.length) return <p>Ссылок на фрагменты извлечения нет.</p>;
  return <div className={styles.panel}>
    {results.map((result, index) => <section key={ids[index]} className={styles.source}>
      {result.isLoading && <p>Загружаем фрагменты документа…</p>}
      {result.isError && <div className={styles.warning} role="alert">
        <p>{result.error instanceof Error ? result.error.message : 'Не удалось загрузить фрагменты документа.'}</p>
        <Button size="sm" variant="outline" onClick={() => result.refetch()}>Повторить загрузку</Button>
      </div>}
      {result.data && <>
        <h3>{result.data.document_title}</h3>
        {!result.data.sections.length && <p>Фрагменты по сохранённым ссылкам не найдены.</p>}
        {result.data.sections.map((section) => <blockquote key={section.id} className={`${styles.excerpt} ${styles.fullExcerpt}`}>
          <span>{section.label}</span><p>{section.text}</p>
        </blockquote>)}
      </>}
    </section>)}
  </div>;
}
