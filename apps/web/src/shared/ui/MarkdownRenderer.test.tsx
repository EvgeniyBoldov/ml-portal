import { render, screen } from '@testing-library/react';
import MarkdownRenderer from './MarkdownRenderer';

describe('MarkdownRenderer', () => {
  it('renders inline code without block wrapper', () => {
    const { container } = render(<MarkdownRenderer content={'Текст с `reglament` внутри строки'} />);

    expect(screen.getByText('reglament')).toBeInTheDocument();
    expect(container.querySelector('div[class*="codeContainer"]')).not.toBeInTheDocument();
  });

  it('renders fenced code as a highlighted block', () => {
    const { container } = render(<MarkdownRenderer content={'```ts\nconst x = 1;\n```'} />);

    expect(screen.getByText('ts')).toBeInTheDocument();
    expect(container.querySelector('code')?.textContent).toContain('const x = 1;');
    expect(container.querySelector('div[class*="codeContainer"]')).toBeInTheDocument();
  });
});
