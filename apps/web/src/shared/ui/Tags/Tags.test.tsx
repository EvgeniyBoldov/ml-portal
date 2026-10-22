import { fireEvent, render, screen } from '@testing-library/react';
import { Tags } from './Tags';

it('renders selected option labels and only allows adding a catalog option', () => {
  const onChange = vi.fn();
  render(
    <Tags
      value={['company']}
      onChange={onChange}
      placeholder="Выберите проект памяти…"
      options={[
        { value: 'company', label: 'Компания' },
        { value: 'engineering', label: 'Разработка' },
      ]}
    />
  );

  expect(screen.getByText('Компания')).toBeInTheDocument();
  const selector = screen.getByRole('combobox', { name: 'Выберите проект памяти…' });
  expect(selector).toHaveTextContent('Разработка');
  expect(selector).not.toHaveTextContent('Компания');

  fireEvent.change(selector, { target: { value: 'engineering' } });
  expect(onChange).toHaveBeenCalledWith(['company', 'engineering']);
});
