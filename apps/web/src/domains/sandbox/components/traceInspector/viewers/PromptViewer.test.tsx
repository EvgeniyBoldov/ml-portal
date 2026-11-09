import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PromptViewer } from './PromptViewer';

describe('PromptViewer', () => {
  it('renders recorded markdown sections and starts with identity, mission and scope open', () => {
    render(<PromptViewer prompt={{ text: '# Identity\nAgent identity\n# Mission\nDo the task\n# Scope\nAllowed work\n# Catalog\nLong catalog' }} />);

    expect(screen.getByText('Agent identity')).toBeInTheDocument();
    expect(screen.getByText('Do the task')).toBeInTheDocument();
    expect(screen.getByText('Allowed work')).toBeInTheDocument();
    expect(screen.getByText('Long catalog')).not.toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Найти в промпте' })).toBeInTheDocument();
  });

  it('provides a titled full view with the exact original prompt text', async () => {
    const prompt = '# Mission\nKeep this **exact** source.';
    render(<PromptViewer prompt={{ text: prompt }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Полный просмотр' }));
    expect(await screen.findByText('Промпт агента')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Исходный текст' }));
    expect(screen.getByRole('dialog').querySelector('pre')?.textContent).toBe(prompt);
  });

  it('does not split headings inside fenced code blocks', () => {
    const { container } = render(<PromptViewer prompt={{ text: '# Mission\nBefore\n```markdown\n# Example heading\n```\n# Scope\nAfter' }} />);
    expect(container.querySelectorAll('details')).toHaveLength(2);
    expect(container.querySelector('pre')?.textContent).toContain('# Example heading');
    expect(screen.getByText('Before')).toBeInTheDocument();
  });

  it('renders image alt text without creating a remote image element', () => {
    const { container } = render(<PromptViewer prompt={{ text: '# Mission\n![diagram](https://example.test/prompt.png)' }} />);
    expect(screen.getByText('diagram')).toBeInTheDocument();
    expect(container.querySelector('img')).not.toBeInTheDocument();
  });

  it('keeps search and full-view controls together in the stacked toolbar', () => {
    render(<PromptViewer prompt={{ text: '# Mission\nTask' }} />);
    const search = screen.getByRole('textbox', { name: 'Найти в промпте' });
    const action = screen.getByRole('button', { name: 'Полный просмотр' });
    expect(search.parentElement).toBe(action.parentElement);
  });
});
