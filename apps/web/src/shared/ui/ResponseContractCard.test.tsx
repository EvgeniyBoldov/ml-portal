import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ResponseContractCard } from './ResponseContractCard';

describe('ResponseContractCard', () => {
  it('shows coverage for json contracts', () => {
    render(
      <ResponseContractCard
        contract={{
          format: 'json',
          schema: {
            type: 'object',
            properties: {
              kind: { type: 'string' },
              rationale: { type: 'string' },
              agent_slug: { type: ['string', 'null'], x_when: 'kind=call_agent' },
            },
            oneOf: [
              {
                title: 'call_agent',
                required: ['kind', 'rationale', 'agent_slug'],
                properties: { kind: { const: 'call_agent' } },
              },
            ],
          },
          plain_text: null,
          markdown: null,
          examples: [],
          failure_policy: { on_invalid: 'retry' },
        }}
        rulesText="use kind"
        outputRequirementsText=""
      />,
    );

    expect(screen.getByText(/format:/)).toBeInTheDocument();
    expect(screen.getByText(/описано: 1 \/ 3/)).toBeInTheDocument();
    expect(screen.getByText(/не описано: rationale, agent_slug/)).toBeInTheDocument();
    expect(screen.getByText('field')).toBeInTheDocument();
    expect(screen.getByText('condition')).toBeInTheDocument();
    expect(screen.getAllByText('kind').length).toBeGreaterThan(0);
    expect(screen.getByText('rationale')).toBeInTheDocument();
    expect(screen.getByText('agent_slug')).toBeInTheDocument();
    expect(screen.getByText('kind=call_agent')).toBeInTheDocument();
    expect(screen.getByText('response variants')).toBeInTheDocument();
    expect(screen.getByText('variant')).toBeInTheDocument();
    expect(screen.getAllByText('call_agent').length).toBeGreaterThan(0);
    expect(screen.getByText('coverage')).toBeInTheDocument();
    expect(screen.getByText(/missing: agent_slug/)).toBeInTheDocument();
    expect(screen.getByText('contract health:')).toBeInTheDocument();
    expect(screen.getByText(/required fields not described: rationale, agent_slug/)).toBeInTheDocument();
    expect(screen.getByText(/no examples/)).toBeInTheDocument();
  });

  it('renders nested schema fields', () => {
    render(
      <ResponseContractCard
        contract={{
          format: 'json',
          schema: {
            type: 'object',
            properties: {
              facts: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    scope: { type: 'string', enum: ['user', 'chat', 'tenant'] },
                    value: { type: 'string' },
                  },
                },
              },
            },
          },
          plain_text: null,
          markdown: null,
          examples: [],
          failure_policy: { on_invalid: 'retry' },
        }}
      />,
    );

    expect(screen.getByText('facts')).toBeInTheDocument();
    expect(screen.getByText('facts[]')).toBeInTheDocument();
    expect(screen.getByText('facts[].scope')).toBeInTheDocument();
  });

  it('renders plain_text contract body', () => {
    render(
      <ResponseContractCard
        contract={{
          format: 'plain_text',
          schema: null,
          plain_text: { criteria: ['grounded'], forbidden: ['traceback'] },
          markdown: null,
          examples: [],
          failure_policy: { on_invalid: 'accept' },
        }}
      />,
    );

    expect(screen.getByText(/plain_text/)).toBeInTheDocument();
    expect(screen.getByText(/grounded/)).toBeInTheDocument();
    expect(screen.getByText('contract health:')).toBeInTheDocument();
    expect(screen.getByText(/contract valid/)).toBeInTheDocument();
  });
});
