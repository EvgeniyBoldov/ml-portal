import { describe, it, expect } from 'vitest';
import { 
  formatDate, 
  formatRelativeTime, 
  truncateText, 
  generateId, 
  debounce,
  throttle,
  isValidEmail,
  isValidPassword,
  sanitizeHtml
} from '../../shared/lib/utils';

describe('Utils', () => {
  describe('formatDate', () => {
    it('formats date correctly', () => {
      const date = new Date('2024-01-15T10:30:00Z');
      expect(formatDate(date)).toBe('15.01.2024');
    });

    it('handles different locales', () => {
      const date = new Date('2024-01-15T10:30:00Z');
      expect(formatDate(date, 'en-US')).toBe('1/15/2024');
    });

    it('handles invalid dates', () => {
      expect(formatDate(new Date('invalid'))).toBe('Invalid Date');
    });
  });

  describe('formatRelativeTime', () => {
    it('formats recent time correctly', () => {
      const now = new Date();
      const oneMinuteAgo = new Date(now.getTime() - 60 * 1000);
      expect(formatRelativeTime(oneMinuteAgo)).toBe('1 minute ago');
    });

    it('formats future time correctly', () => {
      const now = new Date();
      const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
      expect(formatRelativeTime(oneHourLater)).toBe('in 1 hour');
    });

    it('handles invalid dates', () => {
      expect(formatRelativeTime(new Date('invalid'))).toBe('Invalid Date');
    });
  });

  describe('truncateText', () => {
    it('truncates long text', () => {
      const longText = 'This is a very long text that should be truncated';
      expect(truncateText(longText, 20)).toBe('This is a very long...');
    });

    it('returns original text if shorter than limit', () => {
      const shortText = 'Short text';
      expect(truncateText(shortText, 20)).toBe('Short text');
    });

    it('handles empty string', () => {
      expect(truncateText('', 10)).toBe('');
    });

    it('uses custom suffix', () => {
      const longText = 'This is a very long text';
      expect(truncateText(longText, 10, '...')).toBe('This is...');
    });
  });

  describe('generateId', () => {
    it('generates unique IDs', () => {
      const id1 = generateId();
      const id2 = generateId();
      expect(id1).not.toBe(id2);
    });

    it('generates IDs with correct length', () => {
      const id = generateId();
      expect(id).toHaveLength(8);
    });

    it('generates IDs with custom length', () => {
      const id = generateId(12);
      expect(id).toHaveLength(12);
    });

    it('generates alphanumeric IDs', () => {
      const id = generateId();
      expect(id).toMatch(/^[a-zA-Z0-9]+$/);
    });
  });

  describe('debounce', () => {
    it('delays function execution', async () => {
      const mockFn = vi.fn();
      const debouncedFn = debounce(mockFn, 100);
      
      debouncedFn();
      debouncedFn();
      debouncedFn();
      
      expect(mockFn).not.toHaveBeenCalled();
      
      await new Promise(resolve => setTimeout(resolve, 150));
      expect(mockFn).toHaveBeenCalledTimes(1);
    });

    it('cancels previous calls', async () => {
      const mockFn = vi.fn();
      const debouncedFn = debounce(mockFn, 100);
      
      debouncedFn();
      await new Promise(resolve => setTimeout(resolve, 50));
      
      debouncedFn();
      await new Promise(resolve => setTimeout(resolve, 150));
      
      expect(mockFn).toHaveBeenCalledTimes(1);
    });
  });

  describe('throttle', () => {
    it('limits function execution frequency', async () => {
      const mockFn = vi.fn();
      const throttledFn = throttle(mockFn, 100);
      
      throttledFn();
      throttledFn();
      throttledFn();
      
      expect(mockFn).toHaveBeenCalledTimes(1);
      
      await new Promise(resolve => setTimeout(resolve, 150));
      throttledFn();
      
      expect(mockFn).toHaveBeenCalledTimes(2);
    });
  });

  describe('isValidEmail', () => {
    it('validates correct email addresses', () => {
      expect(isValidEmail('test@example.com')).toBe(true);
      expect(isValidEmail('user.name@domain.co.uk')).toBe(true);
      expect(isValidEmail('user+tag@example.org')).toBe(true);
    });

    it('rejects invalid email addresses', () => {
      expect(isValidEmail('invalid-email')).toBe(false);
      expect(isValidEmail('@example.com')).toBe(false);
      expect(isValidEmail('test@')).toBe(false);
      expect(isValidEmail('')).toBe(false);
    });
  });

  describe('isValidPassword', () => {
    it('validates strong passwords', () => {
      expect(isValidPassword('Password123!')).toBe(true);
      expect(isValidPassword('MyStr0ng#Pass')).toBe(true);
    });

    it('rejects weak passwords', () => {
      expect(isValidPassword('password')).toBe(false);
      expect(isValidPassword('12345678')).toBe(false);
      expect(isValidPassword('Password')).toBe(false);
      expect(isValidPassword('')).toBe(false);
    });

    it('checks minimum length', () => {
      expect(isValidPassword('Pass1!')).toBe(false); // Too short
      expect(isValidPassword('Password1!')).toBe(true); // Long enough
    });
  });

  describe('sanitizeHtml', () => {
    it('removes dangerous HTML tags', () => {
      const dangerousHtml = '<script>alert("xss")</script><p>Safe content</p>';
      expect(sanitizeHtml(dangerousHtml)).toBe('<p>Safe content</p>');
    });

    it('preserves safe HTML tags', () => {
      const safeHtml = '<p>Safe <strong>content</strong></p>';
      expect(sanitizeHtml(safeHtml)).toBe('<p>Safe <strong>content</strong></p>');
    });

    it('removes dangerous attributes', () => {
      const dangerousHtml = '<img src="image.jpg" onerror="alert(\'xss\')">';
      expect(sanitizeHtml(dangerousHtml)).toBe('<img src="image.jpg">');
    });

    it('handles empty input', () => {
      expect(sanitizeHtml('')).toBe('');
    });
  });
});
