import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Modal from './Modal';

function DialogHarness() {
  const [open, setOpen] = useState(false);
  const [nestedOpen, setNestedOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Открыть</button>
      <Modal open={open} onClose={() => setOpen(false)} title="Первое окно">
        <input aria-label="Название" autoFocus />
        <button onClick={() => setNestedOpen(true)}>Вложенное окно</button>
        <Modal
          open={nestedOpen}
          onClose={() => setNestedOpen(false)}
          title="Второе окно"
        >
          <input aria-label="Вложенное поле" />
        </Modal>
      </Modal>
    </>
  );
}

describe('Modal keyboard lifecycle', () => {
  it('honours initial autofocus, traps tab in both directions and restores the opener on Escape', async () => {
    const user = userEvent.setup();
    render(<DialogHarness />);
    const opener = screen.getByRole('button', { name: 'Открыть' });
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Первое окно' });
    const input = screen.getByLabelText('Название');
    const close = within(dialog).getByRole('button', { name: 'Закрыть' });
    const last = screen.getByRole('button', { name: 'Вложенное окно' });
    expect(input).toHaveFocus();
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('closes only the topmost modal and restores focus to the parent dialog', async () => {
    const user = userEvent.setup();
    render(<DialogHarness />);
    await user.click(screen.getByRole('button', { name: 'Открыть' }));
    const nestedOpener = screen.getByRole('button', { name: 'Вложенное окно' });
    await user.click(nestedOpener);
    const parent = screen.getByRole('dialog', { name: 'Первое окно' });
    const child = screen.getByRole('dialog', { name: 'Второе окно' });
    expect(parent.getAttribute('aria-labelledby')).not.toEqual(
      child.getAttribute('aria-labelledby')
    );
    expect(screen.getByLabelText('Вложенное поле')).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(
      screen.queryByRole('dialog', { name: 'Второе окно' })
    ).not.toBeInTheDocument();
    expect(parent).toBeInTheDocument();
    expect(nestedOpener).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('retains focus on content updates and uses the latest close callback', async () => {
    const user = userEvent.setup();
    const firstClose = vi.fn();
    const latestClose = vi.fn();
    const view = render(
      <Modal open title="Редактор" onClose={firstClose}>
        <input aria-label="Имя" />
      </Modal>
    );
    const input = screen.getByLabelText('Имя');
    await user.type(input, 'Черновик');
    view.rerender(
      <Modal open title="Редактор" onClose={latestClose}>
        <input aria-label="Имя" />
      </Modal>
    );
    expect(input).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(firstClose).not.toHaveBeenCalled();
    expect(latestClose).toHaveBeenCalledOnce();
  });

  it('lets a child consume Escape before closing the modal', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(
      <Modal open title="Редактор" onClose={close}>
        <input
          aria-label="Поиск"
          onKeyDown={event => {
            if (event.key === 'Escape') event.preventDefault();
          }}
        />
      </Modal>
    );
    await user.keyboard('{Escape}');
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('allows focus in a portaled menu opened from the modal', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(
      <Modal open title="Меню" onClose={close}>
        <input aria-label="Поле" />
        {createPortal(
          <div role="menu">
            <button
              role="menuitem"
              onKeyDown={event => {
                if (event.key === 'Escape') event.preventDefault();
              }}
            >
              Выбрать
            </button>
          </div>,
          document.body
        )}
      </Modal>
    );
    const option = screen.getByRole('menuitem');
    option.focus();
    expect(option).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(close).not.toHaveBeenCalled();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Закрыть' })).toHaveFocus();
  });

  it('redirects programmatic focus from outside the active dialog', async () => {
    const user = userEvent.setup();
    render(<DialogHarness />);
    const opener = screen.getByRole('button', { name: 'Открыть' });
    await user.click(opener);
    opener.focus();
    expect(screen.getByLabelText('Название')).toHaveFocus();
  });
});
