/**
 * ConfirmWriteDialog — modal for confirming/rejecting write tool calls.
 * Shows action details from the CONFIRMATION_REQUIRED SSE event.
 */
import Modal from '@/shared/ui/Modal';
import Button from '@/shared/ui/Button';
import type { SandboxSSEEvent } from '../types';

interface Props {
  event: SandboxSSEEvent;
  onConfirm: () => void;
  onReject: () => void;
}

export default function ConfirmWriteDialog({ event, onConfirm, onReject }: Props) {
  const reason = (event.reason as string) ?? 'Инструмент запрашивает запись данных';
  const action = event.action as Record<string, unknown> | undefined;
  const toolName = (action?.tool_slug as string) ?? (action?.name as string) ?? 'unknown';

  return (
    <Modal open onClose={onReject} title="Подтверждение записи">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '8px 0' }}>
        <p style={{ margin: 0, fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.5 }}>
          {reason}
        </p>

        {action && (
          <div
            style={{
              background: 'var(--bg-secondary)',
              borderRadius: 8,
              padding: '12px 14px',
              fontSize: 13,
              fontFamily: 'monospace',
              color: 'var(--text-primary)',
              maxHeight: 200,
              overflow: 'auto',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)', fontSize: 11, textTransform: 'uppercase' }}>
              Инструмент: {toolName}
            </div>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {JSON.stringify(action, null, 2)}
            </pre>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
          <Button variant="outline" size="sm" onClick={onReject}>
            Отклонить
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            Подтвердить запись
          </Button>
        </div>
      </div>
    </Modal>
  );
}
