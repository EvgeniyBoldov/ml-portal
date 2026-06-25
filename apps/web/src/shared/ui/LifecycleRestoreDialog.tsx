import LifecycleDeleteDialog from './LifecycleDeleteDialog';
import type { LifecycleKind, LifecycleReportResponse } from '@/shared/api/lifecycle';

type Props = {
  open: boolean;
  kind: LifecycleKind;
  entityId: string;
  entityLabel: string;
  isPlatformDefault?: boolean;
  onCancel: () => void;
  onSuccess: (report: LifecycleReportResponse) => void;
};

export default function LifecycleRestoreDialog(props: Props) {
  return <LifecycleDeleteDialog {...props} action="restore" />;
}
