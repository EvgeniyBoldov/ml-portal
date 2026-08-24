import { InspectorFieldGroup, InspectorFieldRow, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { TraceExecutorInfoView, TraceExecutorStatistic } from '../../../traceProjection';

const number = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);
const duration = (value: number): string => value >= 1000 ? `${(value / 1000).toFixed(1)} с` : `${value} мс`;
const tone = (status: TraceExecutorInfoView['status']): 'neutral' | 'success' | 'warn' | 'danger' | 'info' => (
  status === 'completed' ? 'success' : ['failed', 'unfulfillable', 'aborted'].includes(status) ? 'danger' : ['waiting', 'paused'].includes(status) ? 'warn' : 'info'
);

function StatisticValue({ statistic }: { statistic: TraceExecutorStatistic }) {
  const value = statistic.key === 'tokens_total'
    ? `${number(statistic.value)}${statistic.input !== undefined || statistic.output !== undefined ? ` · in ${number(statistic.input ?? 0)} / out ${number(statistic.output ?? 0)}` : ''}`
    : number(statistic.value);
  const limit = statistic.limit;
  if (!limit) return <InspectorScalar value={value} />;
  const badgeTone = limit.status === 'exceeded' ? 'danger' : limit.status === 'neutral' ? 'neutral' : 'success';
  const limitText = `${number(limit.used ?? statistic.value)} / ${number(limit.limit ?? 0)}${limit.remaining !== undefined ? `, осталось ${number(limit.remaining)}` : ''}`;
  return <><InspectorScalar value={value} /> <InspectorStatus label={limitText} tone={badgeTone} /></>;
}

export function ExecutorInfoViewer({ info }: { info: TraceExecutorInfoView }) {
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={info.statusLabel} tone={tone(info.status)} /></InspectorFieldRow>
    {info.durationMs !== undefined ? <InspectorFieldRow label="Длительность"><InspectorScalar value={duration(info.durationMs)} /></InspectorFieldRow> : null}
    {info.statistics.map((statistic) => <InspectorFieldRow key={statistic.key} label={statistic.label}><StatisticValue statistic={statistic} /></InspectorFieldRow>)}
  </InspectorFieldGroup>;
}
