import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders with default message', () => {
    render(<EmptyState />);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });

  it('renders with custom message', () => {
    const customMessage = 'No chats found';
    render(<EmptyState message={customMessage} />);
    expect(screen.getByText(customMessage)).toBeInTheDocument();
  });

  it('renders with custom icon', () => {
    const customIcon = '📭';
    render(<EmptyState icon={customIcon} />);
    expect(screen.getByText(customIcon)).toBeInTheDocument();
  });

  it('renders action button when provided', () => {
    const handleAction = vi.fn();
    render(
      <EmptyState 
        actionLabel="Create Chat" 
        onAction={handleAction}
      />
    );
    
    const button = screen.getByRole('button', { name: 'Create Chat' });
    expect(button).toBeInTheDocument();
    
    fireEvent.click(button);
    expect(handleAction).toHaveBeenCalledTimes(1);
  });

  it('renders with custom size', () => {
    const { rerender } = render(<EmptyState size="small" />);
    expect(screen.getByTestId('empty-state')).toHaveClass('small');
    
    rerender(<EmptyState size="medium" />);
    expect(screen.getByTestId('empty-state')).toHaveClass('medium');
    
    rerender(<EmptyState size="large" />);
    expect(screen.getByTestId('empty-state')).toHaveClass('large');
  });

  it('applies custom className', () => {
    render(<EmptyState className="custom-class" />);
    expect(screen.getByTestId('empty-state')).toHaveClass('custom-class');
  });

  it('renders with description when provided', () => {
    const description = 'Start by creating your first chat';
    render(<EmptyState description={description} />);
    expect(screen.getByText(description)).toBeInTheDocument();
  });

  it('renders with multiple actions', () => {
    const handleAction1 = vi.fn();
    const handleAction2 = vi.fn();
    
    render(
      <EmptyState 
        actions={[
          { label: 'Action 1', onClick: handleAction1 },
          { label: 'Action 2', onClick: handleAction2 }
        ]}
      />
    );
    
    expect(screen.getByRole('button', { name: 'Action 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Action 2' })).toBeInTheDocument();
    
    fireEvent.click(screen.getByRole('button', { name: 'Action 1' }));
    expect(handleAction1).toHaveBeenCalledTimes(1);
    
    fireEvent.click(screen.getByRole('button', { name: 'Action 2' }));
    expect(handleAction2).toHaveBeenCalledTimes(1);
  });
});
