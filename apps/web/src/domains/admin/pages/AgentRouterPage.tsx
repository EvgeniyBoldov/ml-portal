import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { agentsApi, type Agent } from '@/shared/api/agents';
import { useErrorToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import { Badge, Button, ContentBlock, Input, Textarea } from '@/shared/ui';
import styles from './AgentRouterPage.module.css';

interface RouteForm {
  request_text: string;
  category: string;
  tag: string;
}

export function AgentRouterPage() {
  const showError = useErrorToast();
  const [form, setForm] = useState<RouteForm>({
    request_text: '',
    category: '',
    tag: '',
  });
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);

  const routeMutation = useMutation({
    mutationFn: () =>
      agentsApi.route({
        request_text: form.request_text,
        category: form.category || undefined,
        tag: form.tag || undefined,
      }),
    onSuccess: (response) => {
      setSelectedAgent(response.selected_agent);
    },
    onError: (error: Error) => {
      setSelectedAgent(null);
      showError(error.message || 'Не удалось выбрать агента');
    },
  });

  const handleRoute = () => {
    if (!form.request_text.trim()) {
      showError('Введите текст запроса для маршрутизации');
      return;
    }
    routeMutation.mutate();
  };

  return (
    <EntityPageV2 title="Agent Router" mode="view" saving={routeMutation.isPending}>
      <Tab
        title="Маршрутизация"
        layout="single"
        actions={[
          <Button key="route" variant="primary" onClick={handleRoute} disabled={routeMutation.isPending}>
            {routeMutation.isPending ? 'Подбираем...' : 'Подобрать агента'}
          </Button>,
        ]}
      >
        <ContentBlock title="Входные параметры" icon="sparkles">
          <div className={styles['router-form']}>
            <div className={styles['field-item']}>
              <label className={styles.label}>Запрос</label>
              <Textarea
                value={form.request_text}
                onChange={(event) => setForm((prev) => ({ ...prev, request_text: event.target.value }))}
                placeholder="Например: Подбери мне стратегию для SLA инцидентов в проде"
                rows={4}
              />
            </div>
            <div className={styles['field-item']}>
              <label className={styles.label}>Категория (optional)</label>
              <Input
                value={form.category}
                onChange={(event) => setForm((prev) => ({ ...prev, category: event.target.value }))}
                placeholder="support"
              />
            </div>
            <div className={styles['field-item']}>
              <label className={styles.label}>Тег (optional)</label>
              <Input
                value={form.tag}
                onChange={(event) => setForm((prev) => ({ ...prev, tag: event.target.value }))}
                placeholder="incident"
              />
            </div>
          </div>
        </ContentBlock>

        <ContentBlock title="Результат" icon="activity">
          {selectedAgent ? (
            <div className={styles['result-card']}>
              <div className={styles['result-title']}>{selectedAgent.name}</div>
              <div className={styles['result-meta']}>
                <Badge tone="info">{selectedAgent.slug}</Badge>
                <Badge tone={selectedAgent.is_routable ? 'success' : 'neutral'}>
                  {selectedAgent.is_routable ? 'Routable' : 'Manual only'}
                </Badge>
              </div>
              <div className={styles['result-description']}>
                {selectedAgent.description || 'Без описания'}
              </div>
            </div>
          ) : (
            <div className={styles['empty-state']}>
              После запуска маршрутизации здесь появится выбранный агент.
            </div>
          )}
        </ContentBlock>
      </Tab>
    </EntityPageV2>
  );
}

export default AgentRouterPage;
