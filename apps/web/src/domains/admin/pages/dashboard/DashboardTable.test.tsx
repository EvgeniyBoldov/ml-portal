import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { DashboardTable } from './DashboardTable';

afterEach(cleanup);

it('changes the visible page size from the compact overview', () => {
  const rows = Array.from({ length: 7 }, (_, index) => ({
    id: index,
    name: `Agent ${index + 1}`,
  }));
  render(
    <DashboardTable
      columns={[{ key: 'name', label: 'Агент' }]}
      data={rows}
      keyField="id"
    />
  );
  expect(screen.getByText('Agent 5')).toBeInTheDocument();
  expect(screen.queryByText('Agent 7')).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox'), { target: { value: '10' } });
  expect(screen.getByText('Agent 7')).toBeInTheDocument();
});
