import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ToolRequest, ToolResponse } from './CallViews';

describe('ToolRequest', () => {
  it('shows human labels for reference-only arguments without leaking UUIDs in fallback JSON', () => {
    const artifactId = '8d142b7d-2365-40ec-91d6-a4f60f1a2234';
    const resultId = 'b7aaf8a0-3118-4c7f-8d41-4e4fa3776b92';
    render(<ToolRequest value={{ artifact_id: artifactId, result_id: resultId }} />);

    expect(screen.getByText('Выбранный файл')).toBeInTheDocument();
    expect(screen.getByText('Ранее полученный набор данных')).toBeInTheDocument();
    expect(screen.queryByText(artifactId)).not.toBeInTheDocument();
    expect(screen.queryByText(resultId)).not.toBeInTheDocument();
    expect(screen.queryByText(/8d142b7d|b7aaf8a0/)).not.toBeInTheDocument();
  });

  it('keeps a UUID-only argument semantic through its neutral human label without showing raw data', () => {
    const collectionId = 'b91ba775-df53-4ff1-b1dd-4aa8237ab2e0';
    render(<ToolRequest value={{ collection_id: collectionId }} />);
    expect(screen.getByText('Выбранная коллекция')).toBeInTheDocument();
    expect(screen.queryByText(collectionId)).not.toBeInTheDocument();
    expect(screen.queryByText(/b91ba775/)).not.toBeInTheDocument();
  });
});

describe('ToolResponse', () => {
  it('shows direct result data and completeness facts without repeating page metadata', () => {
    const call = {
      info: { status: 'completed' },
      requestView: { toolName: 'search' },
      responseView: { toolResult: {
        success: true, summary: 'Получено', truncated: false,
        data: { value: [{ name: 'Запись' }], meta: { total: 4, complete: false, has_next: true } },
        returnedCount: 1, sourceTotal: 4, sourceComplete: false, inlineComplete: true,
      } },
    };
    render(<ToolResponse call={call as never} />);
    expect(screen.getByText('Запись')).toBeInTheDocument();
    expect(screen.getByText('1 / 4')).toBeInTheDocument();
    expect(screen.queryByText('Данные для агента')).not.toBeInTheDocument();
  });

  it('renders complete recorded model data in place of the store descriptor', () => {
    const call = { info: { status: 'completed' }, requestView: { toolName: 'result.sql' }, responseView: { toolResult: {
      success: true, summary: '', data: { row_count: 1 }, delivery: 'stored', resultId: 'id',
      storedDescriptor: true, returnedCount: 1, inlineComplete: true, inlineDataAvailable: true,
      inlineData: [{ device_type: 'C9200', device_count: 13 }], truncated: false,
    } } };
    render(<ToolResponse call={call as never} sessionId="session" runId="run" />);
    expect(screen.getByText('C9200')).toBeInTheDocument();
    expect(screen.getByText('13')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.queryByText('Показать результат в Store')).not.toBeInTheDocument();
  });
});
