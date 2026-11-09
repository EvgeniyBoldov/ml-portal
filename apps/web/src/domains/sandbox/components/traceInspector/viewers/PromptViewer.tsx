import { useEffect, useMemo, useState } from 'react';
import { InspectorNotice } from '@/shared/ui/Inspector';
import { Input, MarkdownRenderer, Modal } from '@/shared/ui';
import type { TracePrompt } from '../../../traceProjection';
import styles from './PromptViewer.module.css';

type PromptSection = { title: string; content: string };

function splitPrompt(text: string): PromptSection[] {
  const lines = text.split(/\r?\n/);
  const sections: PromptSection[] = [];
  let title = 'Промпт';
  let content: string[] = [];
  let foundHeading = false;
  let activeFence: { marker: string; length: number } | null = null;
  for (const line of lines) {
    const fence = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
    if (activeFence) {
      content.push(line);
      if (fence && fence[1][0] === activeFence.marker && fence[1].length >= activeFence.length && /^\s{0,3}[`~]{3,}\s*$/.test(line)) activeFence = null;
      continue;
    }
    if (fence) {
      activeFence = { marker: fence[1][0], length: fence[1].length };
      content.push(line);
      continue;
    }
    const match = /^(#{1,3})\s+(.+?)\s*$/.exec(line);
    if (match) {
      foundHeading = true;
      if (content.length || sections.length) sections.push({ title, content: content.join('\n').trim() });
      title = match[2];
      content = [];
    } else {
      content.push(line);
    }
  }
  if (content.length || !sections.length) sections.push({ title, content: content.join('\n').trim() });
  return foundHeading ? sections.filter(section => section.content) : [{ title: 'Промпт', content: text }];
}

function isPrimarySection(title: string): boolean {
  return /identity|mission|scope|идентичность|миссия|область|задача|^промпт$/i.test(title);
}

export function PromptViewer({ prompt }: { prompt?: TracePrompt }) {
  const [search, setSearch] = useState('');
  const [isFullViewOpen, setIsFullViewOpen] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  useEffect(() => {
    const handleSectionChange = () => setIsFullViewOpen(false);
    document.addEventListener('agent-inspector-section-change', handleSectionChange);
    return () => document.removeEventListener('agent-inspector-section-change', handleSectionChange);
  }, []);
  const sections = useMemo(() => prompt?.text ? splitPrompt(prompt.text) : [], [prompt?.text]);
  const visibleSections = sections.filter(section => !search.trim() || (section.title + '\n' + section.content).toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));

  if (!prompt?.text) {
    if (prompt?.hash) return <InspectorNotice tone="neutral" title="Промпт скрыт" message="В журнале сохранён только хеш системного промпта." code={prompt.hash} />;
    return <InspectorNotice tone="neutral" message="Эффективный системный промпт для этого исполнителя не записан в журнал." />;
  }

  return <div className={styles.root}>
    <div className={styles.toolbar}>
      <Input value={search} onChange={event => setSearch(event.target.value)} placeholder="Найти в промпте" aria-label="Найти в промпте" />
      <button type="button" className={styles.action} onClick={() => { setShowOriginal(false); setIsFullViewOpen(true); }}>Полный просмотр</button>
    </div>
    <div className={styles.sections}>
      {visibleSections.map((section, index) => {
        const primary = isPrimarySection(section.title);
        return <details key={index + ':' + section.title} open={primary || undefined} className={styles.section}>
          <summary>{section.title}</summary>
          <MarkdownRenderer content={section.content} allowImages={false} />
        </details>;
      })}
      {!visibleSections.length ? <p className={styles.empty}>Совпадений нет.</p> : null}
    </div>
    <Modal open={isFullViewOpen} title="Промпт агента" onClose={() => setIsFullViewOpen(false)} size="xl">
      <div className={styles.modalToolbar}>
        <button type="button" className={styles.action} onClick={() => setShowOriginal(value => !value)}>{showOriginal ? 'Показать документ' : 'Исходный текст'}</button>
      </div>
      {showOriginal ? <pre className={styles.original}>{prompt.text}</pre> : <div className={styles.fullDocument}>{sections.map((section, index) => <section key={index + ':' + section.title}><h3>{section.title}</h3><MarkdownRenderer content={section.content} allowImages={false} /></section>)}</div>}
    </Modal>
  </div>;
}
