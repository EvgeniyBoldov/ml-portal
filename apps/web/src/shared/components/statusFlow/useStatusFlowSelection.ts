import { useEffect, useState } from 'react';

import type { FlowGraphModel, FlowSelection } from './types';
import { pickDefaultFlowSelection } from './statusFlowUtils';

export function useStatusFlowSelection(model: FlowGraphModel) {
  const [selection, setSelection] = useState<FlowSelection>(() => pickDefaultFlowSelection(model));

  useEffect(() => {
    const next = pickDefaultFlowSelection(model);
    setSelection((current) => {
      if (!current.nodeKey) return next;

      const pipelineHasCurrent = model.pipeline.some((node) => node.key === current.nodeKey);
      const laneHasCurrent = (model.lanes ?? []).some((lane) => lane.items.some((item) => item.key === current.nodeKey));
      if (pipelineHasCurrent || laneHasCurrent) {
        return current;
      }
      return next;
    });
  }, [model]);

  return {
    selection,
    setSelection,
  };
}
