import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RAGSources from './RAGSources';

describe('RAGSources', () => {
  it('renders projected excerpts and routes explicit source kinds correctly', () => {
    render(<RAGSources sources={[
      { source_id: 'opaque-1', source_name: 'Opaque source', excerpt: 'Projected excerpt' },
      { source_id: 'https://example.test/doc', source_name: 'Web page', url: 'https://example.test/doc', page: 1 },
      { source_id: 'artifact-1', source_name: 'Report', artifact_id: 'artifact-1' },
      { source_id: 'rag-doc-1', source_name: 'RAG doc', chunk_id: 'chunk-1', text: 'Legacy excerpt' },
    ]} />);
    fireEvent.click(screen.getByRole('button', { name: /Opaque source/ }));
    expect(screen.getByText('Projected excerpt')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Web page/ }));
    expect(screen.getByRole('link', { name: 'Открыть источник' })).toHaveAttribute('href', 'https://example.test/doc');
    expect(screen.queryByRole('button', { name: 'Оригинал' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Report/ }));
    expect(screen.getByRole('link', { name: 'Скачать файл' })).toHaveAttribute('href', expect.stringContaining('/files/artifact-1/download'));
    fireEvent.click(screen.getByRole('button', { name: /RAG doc/ }));
    expect(screen.getByText('Legacy excerpt')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Оригинал' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Текст' })).toHaveLength(1);
  });
});
