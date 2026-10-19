import { render, screen } from '@testing-library/react';
import { ChatAttachments } from './ChatAttachments';

describe('ChatAttachments', () => {
  it('renders an artifact as a link to its canonical download route', () => {
    render(<ChatAttachments variant="artifact" attachments={[{ artifactId: 'artifact-1', fileName: 'result.xlsx' }]} />);

    expect(screen.getByRole('link', { name: /result.xlsx/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/v1/files/artifact-1/download')
    );
    expect(screen.getByRole('link', { name: /result.xlsx/i })).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: /result.xlsx/i })).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('uses the download URL supplied by the backend', () => {
    render(<ChatAttachments variant="artifact" attachments={[{ artifactId: 'artifact-1', fileName: 'result.xlsx', downloadUrl: '/api/v1/files/artifact-1/download' }]} />);

    expect(screen.getByRole('link', { name: /result.xlsx/i })).toHaveAttribute(
      'href',
      '/api/v1/files/artifact-1/download'
    );
  });
});
