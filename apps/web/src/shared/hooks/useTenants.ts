import { useState, useEffect, useCallback, useRef } from 'react';
import { tenantApi, type Tenant } from '@shared/api/tenant';

export function useTenants() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTenants = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await tenantApi.getTenants({ size: 100 });
      setTenants(response.items);
    } catch (err) {
      console.error('Failed to load tenants:', err);
      setError('Failed to load tenants');
    } finally {
      setLoading(false);
    }
  }, []);

  const hasFetchedRef = useRef(false);

  useEffect(() => {
    if (hasFetchedRef.current) {
      return;
    }
    hasFetchedRef.current = true;
    loadTenants();
  }, [loadTenants]);

  return { tenants, loading, error, refetch: loadTenants };
}
