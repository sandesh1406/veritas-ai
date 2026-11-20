import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import type { Profile } from '@/types';

type AuthResult = { error: string | null; needsConfirmation?: boolean };

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  profile: Profile | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (fullName: string, email: string, password: string) => Promise<AuthResult>;
  sendPasswordReset: (email: string) => Promise<AuthResult>;
  updatePassword: (password: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function authError(action: 'login' | 'signup' | 'reset' | 'password'): string {
  if (action === 'login') return 'We could not sign you in. Check your email and password and try again.';
  if (action === 'signup') return 'We could not create your account. Check your details and try again.';
  if (action === 'reset') return 'If that email is registered, a recovery link will be sent shortly.';
  return 'We could not update your password. Please request a new recovery link and try again.';
}

async function loadProfile(userId: string): Promise<Profile | null> {
  const { data, error } = await supabase.from('profiles').select('id, full_name, email, avatar_url, created_at').eq('id', userId).maybeSingle();
  if (error) {
    console.error('profile load failed', error);
    return null;
  }
  return data as Profile | null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshProfile = async () => {
    if (!session?.user.id) {
      setProfile(null);
      return;
    }
    setProfile(await loadProfile(session.user.id));
  };

  useEffect(() => {
    let mounted = true;
    const initialize = async () => {
      const { data } = await supabase.auth.getSession();
      if (!mounted) return;
      setSession(data.session);
      if (data.session) setProfile(await loadProfile(data.session.user.id));
      setIsLoading(false);
    };
    void initialize();

    const { data: authListener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (!mounted) return;
      setSession(nextSession);
      if (event === 'SIGNED_OUT') {
        setProfile(null);
        setIsLoading(false);
        return;
      }
      void (async () => {
        if (nextSession) setProfile(await loadProfile(nextSession.user.id));
        else setProfile(null);
        setIsLoading(false);
      })();
    });

    return () => {
      mounted = false;
      authListener.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    session,
    user: session?.user ?? null,
    profile,
    isLoading,
    signIn: async (email, password) => {
      const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      return { error: error ? authError('login') : null };
    },
    signUp: async (fullName, email, password) => {
      const { data, error } = await supabase.auth.signUp({ email: email.trim(), password, options: { data: { full_name: fullName.trim() } } });
      if (error) return { error: authError('signup') };
      return { error: null, needsConfirmation: !data.session };
    },
    sendPasswordReset: async (email) => {
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: `${window.location.origin}/reset-password` });
      return { error: error ? authError('reset') : null };
    },
    updatePassword: async (password) => {
      const { error } = await supabase.auth.updateUser({ password });
      return { error: error ? authError('password') : null };
    },
    signOut: async () => {
      await supabase.auth.signOut();
    },
    refreshProfile,
  }), [isLoading, profile, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
