import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AccessibleButton from '../AccessibleButton';

describe('AccessibleButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders button with text', () => {
    render(<AccessibleButton>Click me</AccessibleButton>);
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument();
  });

  it('handles click events', () => {
    const handleClick = vi.fn();
    render(<AccessibleButton onClick={handleClick}>Click me</AccessibleButton>);
    
    fireEvent.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when disabled prop is true', () => {
    render(<AccessibleButton disabled>Disabled button</AccessibleButton>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('shows loading state', () => {
    render(<AccessibleButton loading>Loading button</AccessibleButton>);
    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(<AccessibleButton className="custom-class">Button</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('custom-class');
  });

  it('has proper accessibility attributes', () => {
    render(
      <AccessibleButton aria-label="Custom label" aria-describedby="description">
        Button
      </AccessibleButton>
    );
    
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-label', 'Custom label');
    expect(button).toHaveAttribute('aria-describedby', 'description');
  });

  it('supports different variants', () => {
    const { rerender } = render(<AccessibleButton variant="primary">Primary</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('primary');
    
    rerender(<AccessibleButton variant="secondary">Secondary</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('secondary');
    
    rerender(<AccessibleButton variant="danger">Danger</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('danger');
  });

  it('supports different sizes', () => {
    const { rerender } = render(<AccessibleButton size="small">Small</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('small');
    
    rerender(<AccessibleButton size="medium">Medium</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('medium');
    
    rerender(<AccessibleButton size="large">Large</AccessibleButton>);
    expect(screen.getByRole('button')).toHaveClass('large');
  });
});
