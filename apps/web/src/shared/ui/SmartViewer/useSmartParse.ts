import { useMemo } from 'react';
import type { ParsedNode } from './nodes/types';

const MAX_EMBED_DEPTH = 3;

function tryParseJson(raw: string): unknown | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (!(trimmed[0] === '{' || trimmed[0] === '[')) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function parseValue(value: unknown, embedDepth: number): ParsedNode {
  if (value === null || value === undefined) {
    return { type: 'null' };
  }

  if (typeof value === 'boolean') {
    return { type: 'boolean', value };
  }

  if (typeof value === 'number') {
    return { type: 'number', value };
  }

  if (typeof value === 'string') {
    if (embedDepth < MAX_EMBED_DEPTH) {
      const parsed = tryParseJson(value);
      if (parsed !== null) {
        return {
          type: 'embedded_json',
          parsed: parseValue(parsed, embedDepth + 1),
          raw: value,
        };
      }
    }

    const normalized = value.replace(/\\n/g, '\n');
    if (normalized.includes('\n')) {
      return { type: 'multiline', lines: normalized.split('\n') };
    }

    if (normalized.length > 120) {
      const chunkSize = 120;
      const lines: string[] = [];
      for (let i = 0; i < normalized.length; i += chunkSize) {
        lines.push(normalized.slice(i, i + chunkSize));
      }
      return { type: 'multiline', lines };
    }

    return { type: 'string', value };
  }

  if (Array.isArray(value)) {
    return {
      type: 'array',
      items: value.map((item) => parseValue(item, embedDepth)),
    };
  }

  if (typeof value === 'object') {
    return {
      type: 'object',
      entries: Object.entries(value as Record<string, unknown>).map(([key, val]) => ({
        key,
        node: parseValue(val, embedDepth),
      })),
    };
  }

  return { type: 'string', value: String(value) };
}

export function useSmartParse(value: unknown): ParsedNode {
  return useMemo(() => parseValue(value, 0), [value]);
}

export { parseValue };
