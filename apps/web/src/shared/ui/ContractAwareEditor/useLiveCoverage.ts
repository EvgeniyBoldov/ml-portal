import { useEffect, useMemo, useState } from 'react';

import type { ResponseContract } from '@/shared/api/admin';

type CoverageResult = {
  coverageMap: Map<string, boolean>;
  coveredCount: number;
  totalRequired: number;
  uncoveredFields: string[];
};

type TrackableField = {
  path: string;
  name: string;
};

const IGNORE_KEYS = new Set(['kind', 'rationale']);
const DEBOUNCE_MS = 150;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function hasTrackableShape(schema: Record<string, unknown>): boolean {
  return Boolean(schema.properties) || Boolean(schema.oneOf) || Boolean(schema.items);
}

function collectTrackableFields(
  schema: Record<string, unknown>,
  basePath = '',
  inheritedRequired = false,
  depth = 0,
): TrackableField[] {
  if (depth > 4) return [];
  const fields: TrackableField[] = [];
  const requiredSet = new Set(asStringArray(schema.required));
  const properties = asRecord(schema.properties);
  const oneOf = Array.isArray(schema.oneOf) ? schema.oneOf : [];

  for (const [key, rawValue] of Object.entries(properties)) {
    const subSchema = asRecord(rawValue);
    const path = basePath ? `${basePath}.${key}` : key;
    const required = inheritedRequired || requiredSet.has(key);
    const conditional = typeof subSchema.x_when === 'string' && subSchema.x_when.trim().length > 0;
    const hasChildren = hasTrackableShape(subSchema);

    if ((required || conditional) && !IGNORE_KEYS.has(key)) {
      fields.push({ path, name: key });
    }

    if (hasChildren) {
      fields.push(...collectTrackableFields(subSchema, path, required, depth + 1));
    }

    const items = asRecord(subSchema.items);
    if (Object.keys(items).length > 0) {
      const itemPath = `${path}[]`;
      const itemRequired = inheritedRequired || requiredSet.has(key);
      const itemConditional = typeof items.x_when === 'string' && items.x_when.trim().length > 0;

      if ((itemRequired || itemConditional) && !IGNORE_KEYS.has(key)) {
        fields.push({ path: itemPath, name: key });
      }

      if (hasTrackableShape(items)) {
        fields.push(...collectTrackableFields(items, itemPath, itemRequired, depth + 1));
      }
    }
  }

  for (const variant of oneOf) {
    const variantSchema = asRecord(variant);
    const variantRequiredSet = new Set(asStringArray(variantSchema.required));
    const variantProperties = asRecord(variantSchema.properties);

    for (const [key, rawValue] of Object.entries(variantProperties)) {
      const subSchema = asRecord(rawValue);
      const path = basePath ? `${basePath}.${key}` : key;
      const required = variantRequiredSet.has(key);
      const conditional = typeof subSchema.x_when === 'string' && subSchema.x_when.trim().length > 0;
      const hasChildren = hasTrackableShape(subSchema);

      if ((required || conditional) && !IGNORE_KEYS.has(key)) {
        fields.push({ path, name: key });
      }

      if (hasChildren) {
        fields.push(...collectTrackableFields(subSchema, path, required, depth + 1));
      }

      const items = asRecord(subSchema.items);
      if (Object.keys(items).length > 0) {
        const itemPath = `${path}[]`;
        const itemRequired = required;
        const itemConditional = typeof items.x_when === 'string' && items.x_when.trim().length > 0;

        if ((itemRequired || itemConditional) && !IGNORE_KEYS.has(key)) {
          fields.push({ path: itemPath, name: key });
        }

        if (hasTrackableShape(items)) {
          fields.push(...collectTrackableFields(items, itemPath, itemRequired, depth + 1));
        }
      }
    }
  }

  return fields;
}

function matchesText(text: string, field: TrackableField): boolean {
  const needle = field.name.toLowerCase();
  const haystack = text.toLowerCase();
  if (!needle) return false;
  return haystack.includes(needle) || haystack.includes(field.path.toLowerCase());
}

export function useLiveCoverage(
  text: string,
  outputContract: ResponseContract | null,
): CoverageResult {
  const [debouncedText, setDebouncedText] = useState(text);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedText(text), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  return useMemo(() => {
    if (!outputContract || outputContract.format !== 'json' || !outputContract.schema) {
      return {
        coverageMap: new Map<string, boolean>(),
        coveredCount: 0,
        totalRequired: 0,
        uncoveredFields: [],
      };
    }

    const fields = collectTrackableFields(asRecord(outputContract.schema));
    const coverageMap = new Map<string, boolean>();
    const uniqueFields = new Map<string, TrackableField>();

    for (const field of fields) {
      uniqueFields.set(field.path, field);
    }

    for (const field of uniqueFields.values()) {
      coverageMap.set(field.path, matchesText(debouncedText, field));
    }

    const uncoveredFields = [...coverageMap.entries()]
      .filter(([, covered]) => !covered)
      .map(([field]) => field);
    const coveredCount = [...coverageMap.values()].filter(Boolean).length;

    return {
      coverageMap,
      coveredCount,
      totalRequired: coverageMap.size,
      uncoveredFields,
    };
  }, [debouncedText, outputContract]);
}
