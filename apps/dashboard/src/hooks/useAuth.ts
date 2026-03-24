import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

export type WorkspaceTier = 'free' | 'creator' | 'enterprise';

function extractTier(user: User | null): WorkspaceTier {
  const raw = user?.app_metadata?.tier;
  if (raw === 'free' || raw === 'enterprise') return raw;
  return 'creator';
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPasswordReset, setShowPasswordReset] = useState(false);

  useEffect(() => {
    if (!supabase) {
      // Supabase not configured — skip auth, treat as authenticated
      setLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        setUser(session?.user ?? null);
        if (event === 'PASSWORD_RECOVERY') {
          setShowPasswordReset(true);
        }
      },
    );

    return () => subscription.unsubscribe();
  }, []);

  const signOut = async () => {
    if (supabase) {
      await supabase.auth.signOut();
    }
    setUser(null);
  };

  const updatePassword = async (newPassword: string) => {
    if (!supabase) return;
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
    setShowPasswordReset(false);
  };

  const dismissPasswordReset = () => setShowPasswordReset(false);

  return {
    user,
    tier: extractTier(user),
    loading,
    signOut,
    authEnabled: !!supabase,
    showPasswordReset,
    updatePassword,
    dismissPasswordReset,
  };
}
