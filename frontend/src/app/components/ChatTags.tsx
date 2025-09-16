import React, { useState } from 'react';
import Modal from '@shared/ui/Modal';
import Input from '@shared/ui/Input';
import Button from '@shared/ui/Button';

export default function ChatTags({
  chatId: _chatId,
  tags,
  onTagsChange,
}: {
  chatId: string;
  tags: string[];
  onTagsChange: (tags: string[]) => void;
}) {
  const [local, setLocal] = useState<string[]>(tags || []);
  const [open, setOpen] = useState(true);
  const [draft, setDraft] = useState('');

  function add() {
    const t = draft.trim();
    if (!t) return;
    if (local.includes(t)) return;
    setLocal([...local, t]);
    setDraft('');
  }
  function remove(t: string) {
    setLocal(local.filter(x => x !== t));
  }

  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      title="Теги"
      footer={
        <>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Закрыть
          </Button>
          <Button
            onClick={() => {
              onTagsChange(local);
              setOpen(false);
            }}
          >
            Сохранить
          </Button>
        </>
      }
    >
      <div
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <Input
          value={draft}
          onChange={e => setDraft(e.target.value)}
          placeholder="Новый тег"
          onKeyDown={e => {
            if (e.key === 'Enter') add();
          }}
        />
        <Button onClick={add}>Добавить</Button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {local.map(t => (
          <span
            key={t}
            style={{
              border: '1px solid rgba(255,255,255,.2)',
              padding: '2px 8px',
              borderRadius: 999,
            }}
          >
            {t}{' '}
            <button
              onClick={() => remove(t)}
              style={{ marginLeft: 6, opacity: 0.7 }}
            >
              ×
            </button>
          </span>
        ))}
        {local.length === 0 && <div style={{ opacity: 0.7 }}>Пока пусто</div>}
      </div>
    </Modal>
  );
}
