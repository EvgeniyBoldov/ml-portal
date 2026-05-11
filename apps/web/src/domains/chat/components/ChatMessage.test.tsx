import { render, screen } from '@testing-library/react';
import { ChatMessage } from './ChatMessage';

vi.mock('@/shared/ui/MarkdownRenderer', () => ({
  default: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}));

describe('ChatMessage', () => {
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
});
