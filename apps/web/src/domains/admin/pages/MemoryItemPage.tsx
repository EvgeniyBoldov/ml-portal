import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { Button, EntityPageV2, Tab } from '@/shared/ui';
import { adminApi } from '@/shared/api/admin';
import MemoryDetail from '@/domains/admin/components/MemoryDetail';

export default function MemoryItemPage() {
  const { itemId, candidateId } = useParams<{ itemId: string; candidateId: string }>();
  const candidate = useQuery({ queryKey: ['admin', 'memory', 'candidate', candidateId],
    queryFn: () => adminApi.getShadowMemoryCandidate(candidateId!), enabled: Boolean(candidateId) });
  const published = useQuery({ queryKey: ['admin', 'memory', 'item', itemId],
    queryFn: () => adminApi.getSemanticMemoryItem(itemId!), enabled: Boolean(itemId) });
  const request = candidateId ? candidate : published;
  const backPath = `/admin/memory?tab=${candidateId ? 'review' : 'memory'}`;
  if (!request.data || request.isError) return <EntityPageV2 title="Память" mode="view" loading={request.isLoading}
    breadcrumbs={[{ label: 'Мемори', href: '/admin/memory' }, { label: candidateId ? 'На проверке' : 'Утверждённая память', href: backPath }, { label: request.isError ? 'Ошибка загрузки' : 'Загрузка' }]}>
    <Tab title="Память" layout="full">{request.isError && <p role="alert">Не удалось загрузить память. <Button variant="outline" onClick={() => request.refetch()}>Повторить</Button></p>}</Tab>
  </EntityPageV2>;
  return <MemoryDetail key={candidateId ?? itemId} candidate={candidateId ? candidate.data : undefined} published={candidateId ? undefined : published.data} />;
}
