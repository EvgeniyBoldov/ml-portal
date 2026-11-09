import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TraceRoutePolicy } from '../../../traceProjection';
import { RoutePolicyViewer } from './RoutePolicyViewer';

describe('RoutePolicyViewer', () => {
  it('does not render opaque recommendation or rule identifiers in either semantic decision form', () => {
    const recommendationId = '12ee0129-bbc1-4c08-93a2-77ef3b9c7a02';
    const ruleId = 'c1e40a13-68db-4a89-aa8e-4d2d3b35b03c';
    const decision: TraceRoutePolicy = {
      status: 'matched', recommendationId, routeHint: 'planner', ruleId,
      signals: [],
    };
    const { rerender } = render(<RoutePolicyViewer decision={decision} />);
    expect(screen.getByText('Планер')).toBeInTheDocument();
    expect(screen.queryByText(recommendationId)).not.toBeInTheDocument();
    expect(screen.queryByText(ruleId)).not.toBeInTheDocument();

    rerender(<RoutePolicyViewer decision={{ route: 'planner', ruleId, matched: true, signals: [] }} />);
    expect(screen.queryByText(recommendationId)).not.toBeInTheDocument();
    expect(screen.queryByText(ruleId)).not.toBeInTheDocument();
  });
});
