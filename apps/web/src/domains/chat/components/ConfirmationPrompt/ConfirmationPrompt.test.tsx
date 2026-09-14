import { fireEvent, render, screen } from '@testing-library/react';

import { ConfirmationPrompt } from './ConfirmationPrompt';

const item = {
  operationFingerprint: 'fingerprint-1',
  toolSlug: 'deploy',
  operation: 'publish',
  riskLevel: 'write',
  argsPreview: '',
  question: 'Подтвердить публикацию изменений?',
  summary: 'Изменения будут опубликованы.',
};

describe('ConfirmationPrompt', () => {
  it('uses the runtime question as its header and emits confirmation/cancellation callbacks', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmationPrompt
        item={item}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );

    expect(
      screen.getByText('Подтвердить публикацию изменений?')
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отменить' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('does not emit an action while a resume request is running', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmationPrompt
        item={item}
        onConfirm={onConfirm}
        onCancel={onCancel}
        disabled
      />
    );

    expect(screen.getByRole('button', { name: 'Отправка...' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Отправка...' }));
    fireEvent.click(screen.getByRole('button', { name: 'Отменить' }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });
});
