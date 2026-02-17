/**
 * Badge helpers for tone conversion
 */

export type BadgeComponentTone = 'success' | 'info' | 'warn' | 'danger' | 'neutral';

export function convertBadgeTone(tone: string): BadgeComponentTone {
  return tone === 'warning' ? 'warn' : tone as BadgeComponentTone;
}
