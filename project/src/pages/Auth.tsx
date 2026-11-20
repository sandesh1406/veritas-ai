import { useState, type FormEvent } from 'react';
import { ArrowRight, CheckCircle2, LockKeyhole, Mail, UserRound } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { BrandLogo } from '@/components/BrandLogo';
import { useAuth } from '@/contexts/AuthContext';

type AuthMode = 'login' | 'signup' | 'forgot' | 'reset';

const copy: Record<AuthMode, { eyebrow: string; title: string; description: string }> = {
  login: { eyebrow: 'Welcome back', title: 'Sign in to Veritas AI', description: 'Continue your evidence-first research workflow.' },
  signup: { eyebrow: 'Create your workspace', title: 'Start verifying with confidence', description: 'Build a secure workspace for your research team.' },
  forgot: { eyebrow: 'Account recovery', title: 'Reset your password', description: 'We will send a secure recovery link to your email.' },
  reset: { eyebrow: 'New password', title: 'Choose a new password', description: 'Use at least 8 characters to keep your workspace protected.' },
};

export function AuthPage({ mode }: { mode: AuthMode }) {
  const { signIn, signUp, sendPasswordReset, updatePassword } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState('');
  const [success, setSuccess] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const content = copy[mode];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage('');
    setSuccess('');
    if (mode === 'signup' && !fullName.trim()) { setMessage('Enter your full name to continue.'); return; }
    if (!email.trim() && mode !== 'reset') { setMessage('Enter your email address to continue.'); return; }
    if (mode === 'signup' && password.length < 8) { setMessage('Your password must be at least 8 characters.'); return; }
    if ((mode === 'signup' || mode === 'reset') && password !== confirmation) { setMessage('Your passwords do not match.'); return; }
    if (mode === 'reset' && password.length < 8) { setMessage('Your password must be at least 8 characters.'); return; }
    setIsSubmitting(true);
    const result = mode === 'login'
      ? await signIn(email, password)
      : mode === 'signup'
        ? await signUp(fullName, email, password)
        : mode === 'forgot'
          ? await sendPasswordReset(email)
          : await updatePassword(password);
    setIsSubmitting(false);
    if (result.error) { setMessage(result.error); return; }
    if (mode === 'signup' && result.needsConfirmation) { setSuccess('Your account is ready. Check your email if confirmation is required, then sign in.'); return; }
    if (mode === 'forgot') { setSuccess('If that email is registered, a recovery link will be sent shortly.'); return; }
    if (mode === 'reset') { setSuccess('Your password has been updated. You can sign in now.'); setTimeout(() => navigate('/login'), 800); return; }
    navigate('/');
  };

  return <main className="auth-page"><div className="auth-glow auth-glow-one" /><div className="auth-glow auth-glow-two" /><div className="auth-brand"><BrandLogo /></div><div className="auth-card"><div className="auth-card-heading"><span className="eyebrow">{content.eyebrow}</span><h1>{content.title}</h1><p>{content.description}</p></div><form className="auth-form" onSubmit={submit}>{mode === 'signup' && <label><span>Full name</span><div className="auth-input"><UserRound size={16} /><input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Your name" autoComplete="name" /></div></label>}{mode !== 'reset' && <label><span>Email address</span><div className="auth-input"><Mail size={16} /><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@research.org" autoComplete="email" /></div></label>}{mode !== 'forgot' && <label><span>{mode === 'reset' ? 'New password' : 'Password'}</span><div className="auth-input"><LockKeyhole size={16} /><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></div></label>}{(mode === 'signup' || mode === 'reset') && <label><span>Confirm password</span><div className="auth-input"><LockKeyhole size={16} /><input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Repeat your password" autoComplete="new-password" /></div></label>}{message && <div className="auth-message auth-error">{message}</div>}{success && <div className="auth-message auth-success"><CheckCircle2 size={16} />{success}</div>}<button className="primary-button auth-submit" disabled={isSubmitting}>{isSubmitting ? 'Working...' : mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create account' : mode === 'forgot' ? 'Send recovery link' : 'Update password'} <ArrowRight size={17} /></button></form><div className="auth-links">{mode === 'login' && <><Link to="/forgot-password">Forgot password?</Link><span>New to Veritas AI? <Link to="/signup">Create an account</Link></span></>}{mode === 'signup' && <span>Already have an account? <Link to="/login">Sign in</Link></span>}{mode === 'forgot' && <span>Remember your password? <Link to="/login">Back to sign in</Link></span>}{mode === 'reset' && <span>Return to <Link to="/login">sign in</Link></span>}</div></div><p className="auth-footer"><LockKeyhole size={13} /> Your research workspace is private by default.</p></main>;
}
