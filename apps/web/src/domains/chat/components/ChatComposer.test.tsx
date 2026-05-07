import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChatComposer } from './ChatComposer';

const getChatUploadPolicyMock = vi.fn().mockResolvedValue({
  max_bytes: 50 * 1024 * 1024,
  allowed_extensions: ['png', 'txt'],
  allowed_content_types_by_extension: { png: ['image/png'], txt: ['text/plain'] },
});

vi.mock('@/shared/api/chats', () => ({
  getChatUploadPolicy: getChatUploadPolicyMock,
}));

describe('ChatComposer', () => {
  const createObjectURL = vi.fn(() => 'blob:preview');
  const revokeObjectURL = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
  });

  it('revokes object URLs after successful send', async () => {
    const onSend = vi.fn();
    const { container } = render(<ChatComposer onSend={onSend} />);
    await waitFor(() => expect(getChatUploadPolicyMock).toHaveBeenCalledTimes(1));
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    const image = new File(['img'], 'img.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [image] } });

    const sendButton = screen.getByRole('button', { name: 'Отправить сообщение' });
    fireEvent.click(sendButton);

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview');
  });

  it('revokes object URLs on unmount', async () => {
    const { container, unmount } = render(<ChatComposer onSend={vi.fn()} />);
    await waitFor(() => expect(getChatUploadPolicyMock).toHaveBeenCalledTimes(1));
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    const image = new File(['img'], 'img.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [image] } });
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    unmount();

    expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview');
  });
});
