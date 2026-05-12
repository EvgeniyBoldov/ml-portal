import { fireEvent, render, screen } from '@testing-library/react';
import { ChatMessage } from './ChatMessage';

vi.mock('@/shared/ui/MarkdownRenderer', () => ({
  default: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}));

describe('ChatMessage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('falls back to content when answer blocks are unknown', () => {
    render(
      <ChatMessage
        role="assistant"
        content="fallback content"
        meta={{ answer_blocks: [{ type: 'unknown_block', value: 'x' }] }}
      />
    );

    expect(screen.getByTestId('markdown')).toHaveTextContent('fallback content');
  });

  it('renders known structured bigstring block', () => {
    render(
      <ChatMessage
        role="assistant"
        content="fallback content"
        meta={{ answer_blocks: [{ type: 'bigstring', value: 'structured value' }] }}
      />
    );

    expect(screen.getByTestId('markdown')).toHaveTextContent('structured value');
    expect(screen.queryByText('fallback content')).not.toBeInTheDocument();
  });

  it('renders markdown fallback content', () => {
    render(
      <ChatMessage
        role="assistant"
        content="**bold** plain"
      />
    );

    expect(screen.getByTestId('markdown')).toHaveTextContent('**bold** plain');
  });

  it('renders runtime run reference when present in meta', () => {
    render(
      <ChatMessage
        role="assistant"
        content="answer"
        meta={{ runtime_run_id: '11111111-1111-1111-1111-111111111111' }}
      />
    );

    expect(screen.getByText(/run 11111111/i)).toBeInTheDocument();
  });

  it('downloads attachment by download_url', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(
      <ChatMessage
        role="assistant"
        content="answer"
        meta={{
          attachments: [
            {
              id: 'att-1',
              file_name: 'report.csv',
              download_url: '/api/v1/files/chatatt_att-1/download',
            },
          ],
        }}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /report.csv/i }));
    expect(openSpy).toHaveBeenCalledWith('/api/v1/files/chatatt_att-1/download', '_blank', 'noopener,noreferrer');
  });

  it('supports legacy attachment url in meta', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(
      <ChatMessage
        role="assistant"
        content="answer"
        meta={{
          attachments: [
            {
              id: 'att-legacy',
              file_name: 'legacy.txt',
              url: '/legacy/signed/url',
            },
          ],
        }}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /legacy.txt/i }));
    expect(openSpy).toHaveBeenCalledWith('/legacy/signed/url', '_blank', 'noopener,noreferrer');
  });
});
