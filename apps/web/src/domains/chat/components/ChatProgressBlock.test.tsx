import { render, screen } from '@testing-library/react';
import { ChatProgressBlock } from './ChatProgressBlock';

describe('ChatProgressBlock', () => {
  it('renders compact progress lines', () => {
    render(<ChatProgressBlock lines={[{ id: '1', text: 'Шаг 1' }, { id: '2', text: 'Шаг 2' }]} />);
    expect(screen.getByText('Шаг 1')).toBeInTheDocument();
    expect(screen.getByText('Шаг 2')).toBeInTheDocument();
  });

  it('renders nothing for empty list', () => {
    const { container } = render(<ChatProgressBlock lines={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
