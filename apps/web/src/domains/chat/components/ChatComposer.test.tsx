import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChatComposer } from './ChatComposer';

const getChatUploadPolicyMock = vi.fn().mockResolvedValue({
  max_bytes: 50 * 1024 * 1024,
  allowed_extensions: ['png', 'txt'],
  allowed_content_types_by_extension: {
    png: ['image/png'],
    txt: ['text/plain'],
  },
});

vi.mock('@/shared/api/chats', () => ({
  getChatUploadPolicy: getChatUploadPolicyMock,
}));

describe('ChatComposer', () => {
  const createObjectURL = vi.fn(() => 'blob:preview');
  const revokeObjectURL = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true,
    });
  });

  it('revokes object URLs after successful send', async () => {
    const onSend = vi.fn();
    const { container } = render(<ChatComposer onSend={onSend} />);
    await waitFor(() =>
      expect(getChatUploadPolicyMock).toHaveBeenCalledTimes(1)
    );
    const fileInput = container.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;

    const image = new File(['img'], 'img.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [image] } });

    const sendButton = screen.getByRole('button', {
      name: 'Отправить сообщение',
    });
    fireEvent.click(sendButton);

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith(
      '',
      expect.objectContaining({ attachments: [image] })
    );
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview')
    );
  });

  it('revokes object URLs on unmount', async () => {
    const { container, unmount } = render(<ChatComposer onSend={vi.fn()} />);
    await waitFor(() =>
      expect(getChatUploadPolicyMock).toHaveBeenCalledTimes(1)
    );
    const fileInput = container.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;

    const image = new File(['img'], 'img.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [image] } });
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    unmount();

    await waitFor(() =>
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview')
    );
  });
});

describe('asynchronous submission', () => {
  it('clears text and attachments immediately and locks the composer while sending', async () => {
    let resolveSend: ((value: boolean) => void) | undefined;
    const onSend = vi.fn(
      () =>
        new Promise<boolean>(resolve => {
          resolveSend = resolve;
        })
    );
    const onStop = vi.fn();
    const { container } = render(
      <ChatComposer onSend={onSend} onStop={onStop} />
    );
    await waitFor(() => expect(getChatUploadPolicyMock).toHaveBeenCalled());
    fireEvent.change(container.querySelector('input[type=file]')!, {
      target: {
        files: [new File(['notes'], 'notes.txt', { type: 'text/plain' })],
      },
    });
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Отправляемый текст' },
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'Отправить сообщение' })
    );

    expect(screen.getByRole('textbox')).toHaveValue('');
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.queryByText('notes.txt')).not.toBeInTheDocument();
    expect(container.querySelector('input[type=file]')).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Остановить генерацию' })
    ).toBeEnabled();
    expect(
      screen.queryByRole('button', { name: 'Отправить сообщение' })
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'Остановить генерацию' })
    );
    expect(onStop).toHaveBeenCalledOnce();

    resolveSend?.(true);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
  });

  it('retains text and attachment after an unsuccessful upload', async () => {
    const onSend = vi.fn().mockResolvedValue(false);
    const { container } = render(<ChatComposer onSend={onSend} />);
    await waitFor(() => expect(getChatUploadPolicyMock).toHaveBeenCalled());
    fireEvent.change(container.querySelector('input[type=file]')!, {
      target: {
        files: [
          new File(['notes'], 'notes.txt', {
            type: 'application/octet-stream',
          }),
        ],
      },
    });
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Исходный текст' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Отправить сообщение' })
    );
    await waitFor(() => expect(onSend).toHaveBeenCalled());
    expect(screen.getByRole('textbox')).toHaveValue('Исходный текст');
    expect(screen.getByText('notes.txt')).toBeInTheDocument();
  });
});

it('restores the latest user message with ArrowUp when the composer is empty', () => {
  render(
    <ChatComposer onSend={vi.fn()} previousMessage="Предыдущее сообщение" />
  );
  const input = screen.getByRole('textbox');
  fireEvent.keyDown(input, { key: 'ArrowUp' });
  expect(input).toHaveValue('Предыдущее сообщение');
});
