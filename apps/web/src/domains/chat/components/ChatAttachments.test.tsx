import { fireEvent, render, screen } from '@testing-library/react';
import { ChatAttachments } from './ChatAttachments';

describe('ChatAttachments', () => {
  it('opens a canonical file reference', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<ChatAttachments variant="artifact" attachments={[{ artifactId: 'artifact-1', fileName: 'result.xlsx' }]} />);

    fireEvent.click(screen.getByRole('button', { name: /result.xlsx/i }));
    expect(open).toHaveBeenCalledWith(expect.stringContaining('/api/v1/files/'), '_blank', 'noopener,noreferrer');
    open.mockRestore();
  });
});
