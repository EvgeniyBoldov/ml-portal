import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PeriodicRunResult } from './PeriodicRunResult';

describe('periodic run result view', () => {
  it('switches between collapsed, brief and complete views without offering copy', () => {
    render(<PeriodicRunResult value={413} scalarLabel="Удалено событий" />);
    const controls = within(
      screen.getByRole('group', { name: 'Режим отображения результата' })
    );
    const collapsed = controls.getByRole('button', { name: 'Свёрнуто' });
    const brief = controls.getByRole('button', { name: 'Кратко' });
    const full = controls.getByRole('button', { name: 'Просмотр' });

    expect(collapsed).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('413')).not.toBeInTheDocument();
    fireEvent.click(brief);
    expect(brief).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Удалено событий')).toBeVisible();
    expect(screen.getByText('413')).toBeVisible();

    fireEvent.click(full);
    expect(full).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('413').tagName).toBe('CODE');
    expect(
      screen.queryByRole('button', { name: 'Копировать' })
    ).not.toBeInTheDocument();

    fireEvent.click(collapsed);
    expect(screen.queryByText('413')).not.toBeInTheDocument();
  });

  it('previews objects by default and keeps their complete result available', () => {
    render(
      <PeriodicRunResult
        value={{
          status: 'disabled',
          reachable: false,
          nested: { count: 2 },
          a: 1,
          b: 2,
          c: 3,
          d: 4,
        }}
      />
    );
    expect(screen.getByRole('button', { name: 'Кратко' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByText('Выключен')).toBeVisible();
    expect(screen.getByText('Нет')).toBeVisible();
    expect(screen.getByText('Полей: 1')).toBeVisible();
    expect(screen.getByText('Показано 6 из 7')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Просмотр' }));
    expect(screen.getByText(/"reachable": false/)).toBeVisible();
    expect(screen.getByText(/"d": 4/)).toBeVisible();
  });
});
