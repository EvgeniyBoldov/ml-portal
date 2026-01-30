/**
 * PolicyViewPage - View execution policy details
 * 
 * Redirects to PolicyEditorPage in view mode
 */
import { Navigate, useParams } from 'react-router-dom';

export function PolicyViewPage() {
  const { id } = useParams<{ id: string }>();
  
  // Redirect to unified editor page in view mode
  return <Navigate to={`/admin/policies/${id}`} replace />;
}

export default PolicyViewPage;
