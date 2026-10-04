import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { Button, EntityPageV2, Tab } from '@/shared/ui';
import { adminApi } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import MemoryTermDetail from '@/domains/admin/components/MemoryTermDetail';

export default function MemoryTermPage() {
  const { termId } = useParams<{ termId: string }>();
  const term = useQuery({ queryKey: qk.admin.glossary.detail(termId!), queryFn: () => adminApi.getGlossaryTerm(termId!) });
  if (!term.data || term.isError) return <EntityPageV2 title="Термин" mode="view" loading={term.isLoading}
    backPath="/admin/memory?tab=glossary" breadcrumbs={[{ label: 'Мемори', href: '/admin/memory' }, { label: 'Термин' }]}>
    <Tab title="Термин" layout="full">{term.isError && <p role="alert">Не удалось загрузить термин. <Button variant="outline" onClick={() => term.refetch()}>Повторить</Button></p>}</Tab>
  </EntityPageV2>;
  return <MemoryTermDetail key={termId} term={term.data} />;
}
