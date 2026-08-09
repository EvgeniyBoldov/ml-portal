import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';

const asRecord = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};

const labels: Record<string, string> = {
  model: 'Модель', temperature: 'Temperature', max_tokens: 'Макс. токенов', streaming_enabled: 'Streaming',
  citations_required: 'Требуются цитаты', allow_parallel_tool_calls: 'Параллельные вызовы инструментов',
};

/** Prepared executor snapshot shown as the effective context of an LLM request. */
export function ExecutionContextViewer({ snapshot }: { snapshot?: unknown }) {
  const root = asRecord(snapshot);
  const config = asRecord(root.config_snapshot ?? root);
  const meta = asRecord(config.meta);
  const prompt = typeof config.system_prompt === 'string' ? config.system_prompt : '';
  const promptHash = typeof config.system_prompt_hash === 'string' ? config.system_prompt_hash : '';
  const settings = Object.entries(meta).filter(([key, value]) => key in labels && value !== null && value !== undefined);
  const operations = Array.isArray(meta.available_operations) ? meta.available_operations : [];
  if (!settings.length && !prompt && !promptHash && !operations.length) return null;
  return <>
    {settings.length ? <InspectorFieldGroup>{settings.map(([key, value]) => <InspectorFieldRow key={key} label={labels[key]}><InspectorScalar value={value as string | number | boolean | null} /></InspectorFieldRow>)}</InspectorFieldGroup> : null}
    {prompt ? <InspectorFieldGroup><InspectorFieldRow label="Системный промпт"><InspectorTextBlock text={prompt} /></InspectorFieldRow></InspectorFieldGroup> : null}
    {!prompt && promptHash ? <InspectorNotice tone="neutral" title="Промпт скрыт" message="В журнале сохранён только хеш системного промпта." code={promptHash} /> : null}
    {operations.length ? <InspectorFieldGroup><InspectorFieldRow label="Доступные операции"><InspectorScalar value={operations.map((value) => String(asRecord(value).operation_slug ?? asRecord(value).canonical_name ?? asRecord(value).title ?? '')).filter(Boolean).join(', ')} /></InspectorFieldRow></InspectorFieldGroup> : null}
  </>;
}
