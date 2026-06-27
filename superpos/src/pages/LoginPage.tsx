import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Icon } from '../components/ui/Icon';

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);

  const login   = useAuthStore(s => s.login);
  const loading = useAuthStore(s => s.loading);
  const error   = useAuthStore(s => s.error);
  const clearError = useAuthStore(s => s.clearError);
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    try {
      await login(username, password);
      // Route by role: cashiers land on POS, managers/admins/owners on the dashboard.
      const role = useAuthStore.getState().user?.role;
      const target = role === 'Cashier' ? '/pos' : '/dashboard';
      navigate(target, { replace: true });
    } catch {
      // error is already in the store; nothing else to do here.
    }
  };

  // Clear server-side error whenever the user edits the form again.
  const onFieldChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    if (error) clearError();
    setter(e.target.value);
  };

  return (
    <div className="min-h-screen grid place-items-center bg-neutral-100 p-6">
      <div className="w-full max-w-[420px]">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-11 h-11 rounded-lg bg-brand-500 grid place-items-center text-white font-bold text-xl shadow-md">S</div>
          <div>
            <div className="text-[22px] font-semibold tracking-tight leading-none">SuperPOS</div>
            <div className="text-[12px] text-neutral-500 mt-1">Cloud retail operating system</div>
          </div>
        </div>

        <Card className="p-7">
          <h1 className="text-[20px] font-semibold mb-1">Sign in to your terminal</h1>
          <p className="text-[13px] text-neutral-500 mb-6">Use your cashier or admin credentials.</p>

          {error && (
            <div
              role="alert"
              aria-live="polite"
              className="mb-4 flex items-start gap-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700"
            >
              <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={submit} className="flex flex-col gap-4">
            <label className="text-[13px] font-semibold text-neutral-700">
              Username
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={onFieldChange(setUsername)}
                required
                disabled={loading}
                className="mt-1.5 w-full h-10 px-3 rounded-md border border-neutral-300 focus-ring bg-white text-[14px] disabled:bg-neutral-50 disabled:text-neutral-400"
              />
            </label>

            <label className="text-[13px] font-semibold text-neutral-700">
              <div className="flex items-center justify-between">
                <span>Password</span>
                <a className="text-[12px] text-brand-600 font-medium hover:underline" href="#">Forgot?</a>
              </div>
              <div className="mt-1.5 relative">
                <input
                  type={show ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={onFieldChange(setPassword)}
                  required
                  disabled={loading}
                  className="w-full h-10 px-3 pe-10 rounded-md border border-neutral-300 focus-ring bg-white text-[14px] disabled:bg-neutral-50 disabled:text-neutral-400"
                />
                <button
                  type="button"
                  onClick={() => setShow(s => !s)}
                  disabled={loading}
                  className="absolute end-2 top-1/2 -translate-y-1/2 w-7 h-7 grid place-items-center rounded text-neutral-500 hover:bg-neutral-100 focus-ring disabled:opacity-40"
                  aria-label={show ? 'Hide password' : 'Show password'}
                >
                  <Icon name={show ? 'eyeOff' : 'eye'} size={16} />
                </button>
              </div>
            </label>

            <label className="flex items-center gap-2 text-[13px] text-neutral-600 select-none">
              <input
                type="checkbox"
                defaultChecked
                disabled={loading}
                className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
              />
              Trust this device for 24 hours
            </label>

            <Button size="lg" type="submit" disabled={loading}>
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full spin" />
                  Signing in…
                </>
              ) : 'Sign in'}
            </Button>
          </form>

          <div className="mt-6 pt-5 border-t border-neutral-200 flex items-center justify-between text-[12px] text-neutral-500">
            <span>v2.0.4 · Terminal POS-01</span>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-success-500" />
              Server reachable
            </span>
          </div>
        </Card>

        <p className="text-center text-[12px] text-neutral-500 mt-5">
          Need help? Call IT at <b className="text-neutral-700">x4001</b> · Branch <b className="text-neutral-700">Cairo Downtown #03</b>
        </p>
      </div>
    </div>
  );
};
