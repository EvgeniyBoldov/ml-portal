import { InspectorNotice, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TracePrompt } from '../../../traceProjection';

/** Effective system prompt selected for an executor, not the full LLM message exchange. */
export function PromptViewer({ prompt }: { prompt?: TracePrompt }) {
  if (prompt?.text) return <InspectorTextBlock text={prompt.text} />;
  if (prompt?.hash) return <InspectorNotice tone="neutral" title="Промпт скрыт" message="В журнале сохранён только хеш системного промпта." code={prompt.hash} />;
  return <InspectorNotice tone="neutral" message="Эффективный системный промпт для этого исполнителя не записан в журнал." />;
}
