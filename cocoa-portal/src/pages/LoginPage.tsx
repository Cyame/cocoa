import { AlertCircle, Building2, LoaderCircle, LogIn, UserPlus } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import { useSessionStore } from '@/stores/session';

type TokenResponse = {
  readonly access_token: string;
  readonly token_type: string;
};

type Mode = 'sign-in' | 'register';

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = useSessionStore((state) => state.token);
  const setToken = useSessionStore((state) => state.setToken);
  const mode: Mode = searchParams.get('mode') === 'register' ? 'register' : 'sign-in';
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (token !== null) {
    return <Navigate to="/offices" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      let endpoint: string;
      let body: Record<string, string>;
      if (mode === 'register') {
        endpoint = '/auth/register';
        body = { username, email, password };
      } else {
        endpoint = '/auth/login';
        body = { username, password };
      }
      const response = await api<TokenResponse>(endpoint, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setToken(response.access_token);
      navigate('/offices', { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        const apiMessage =
          typeof error.payload === 'object' &&
          error.payload !== null &&
          'message' in error.payload &&
          typeof error.payload.message === 'string'
            ? error.payload.message
            : error.message;
        setErrorMessage(apiMessage);
        return;
      }
      throw error;
    } finally {
      setIsSubmitting(false);
    }
  }

  const heading = mode === 'register' ? t('login.registerHeading') : t('login.signInHeading');
  const tagline = mode === 'register' ? t('login.registerTagline') : t('login.signInTagline');
  const submitLabel = mode === 'register' ? t('login.createAccount') : t('login.submit');
  const switchLabel = mode === 'register' ? t('login.switchToSignIn') : t('login.switchToRegister');
  const switchTo: Mode = mode === 'register' ? 'sign-in' : 'register';
  const switchHref = switchTo === 'register' ? '/login?mode=register' : '/login';

  return (
    <main className="grid min-h-dvh place-items-center bg-slate-950 px-4 py-10 text-slate-100">
      <section className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl shadow-black/30 sm:p-8">
        <div className="mb-8 flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-semibold tracking-tight">{t('common.appName')}</p>
            <p className="text-xs text-slate-400">{t('common.appTagline')}</p>
          </div>
        </div>

        <div className="mb-6" role="tablist" aria-label="Authentication mode">
          <h1 className="text-2xl font-semibold tracking-tight">{heading}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">{tagline}</p>
        </div>

        {errorMessage !== null ? (
          <div
            role="alert"
            className="mb-5 flex gap-3 rounded-lg border border-red-800/80 bg-red-950/70 px-4 py-3 text-sm text-red-200"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>{errorMessage}</p>
          </div>
        ) : null}

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="username" className="mb-2 block text-sm font-medium text-slate-200">
              {t('login.username')}
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.currentTarget.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
            />
          </div>

          {mode === 'register' ? (
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-200">
                {t('login.email')}
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
          ) : null}

          <div>
            <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-200">
              {t('login.password')}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.currentTarget.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
            />
            {mode === 'register' ? (
              <p className="mt-1.5 text-xs text-slate-500">{t('login.passwordHint')}</p>
            ) : null}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            aria-busy={isSubmitting}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 disabled:cursor-wait disabled:opacity-60"
          >
            {isSubmitting ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : mode === 'register' ? (
              <UserPlus className="size-4" aria-hidden="true" />
            ) : (
              <LogIn className="size-4" aria-hidden="true" />
            )}
            {submitLabel}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-400">
          <Link to={switchHref} className="text-blue-400 transition-colors hover:text-blue-300">
            {switchLabel}
          </Link>
        </p>
      </section>
    </main>
  );
}
