import React, { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@shared/hooks/useAuth';
import { useNavigate } from 'react-router-dom';

export default function GPTGate({ children }: { children: React.ReactNode }) {
  const { user, hydrate } = useAuth();
  const [checked, setChecked] = useState(false);
  const nav = useNavigate();

  const fetchMe = useCallback(async () => {
    try {
      await hydrate();
    } finally {
      setChecked(true);
    }
  }, [hydrate]);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  useEffect(() => {
    if (checked && !user) nav('/login');
  }, [checked, user, nav]);

  if (!checked) return null;
  if (!user) return null;
  return <>{children}</>;
}
