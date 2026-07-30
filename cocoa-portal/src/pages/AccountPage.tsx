import { AlertCircle, KeyRound, LoaderCircle, User } from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/lib/api';
import {
  type AccountProfile,
  changeAccountPassword,
  fetchAccount,
  updateAccount,
} from '@/lib/api/users';

const IDENTITY_LABEL_KEYS: Record<string, string> = {
  system: 'identity.system',
  org: 'identity.org',
  namespace: 'identity.namespace',
  workspace: 'identity.workspace',
  member: 'identity.member',
};

export default function AccountPage() {
  const { t } = useTranslation();
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [email, setEmail] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchAccount();
      setProfile(data);
      setEmail(data.email);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSaveProfile(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    setErrorMessage(null);
    try {
      const next = await updateAccount({ email });
      setProfile(next);
      setNotice(t('account.saved'));
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordBusy(true);
    setNotice(null);
    setErrorMessage(null);
    try {
      await changeAccountPassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setNotice(t('account.passwordChanged'));
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setPasswordBusy(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 p-16 text-sm text-slate-500">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  const identityKey = profile?.identity ? IDENTITY_LABEL_KEYS[profile.identity] : null;

  return (
    <section className="mx-auto w-full max-w-3xl p-6 lg:p-8" aria-labelledby="account-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
          <User className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 id="account-title" className="text-2xl font-semibold text-slate-950">
            {t('account.title')}
          </h1>
          <p className="mt-1 text-sm text-slate-600">{t('account.subtitle')}</p>
        </div>
      </header>

      {errorMessage ? (
        <div
          role="alert"
          className="mb-4 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}
      {notice ? (
        <p role="status" className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </p>
      ) : null}

      <form
        onSubmit={(e) => void handleSaveProfile(e)}
        className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <h2 className="text-sm font-semibold text-slate-900">{t('account.profile')}</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">{t('account.username')}</span>
            <input
              value={profile?.username ?? ''}
              disabled
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">{t('account.email')}</span>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          {t('account.identity')}:{' '}
          <span className="font-medium text-slate-900">
            {identityKey ? t(identityKey) : t('identity.member')}
          </span>
        </p>
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('account.lockedGenes')}
          </p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {(profile?.locked_genes ?? []).map((g) => (
              <li
                key={g.id}
                className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600"
              >
                {g.slug}
              </li>
            ))}
          </ul>
        </div>
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('account.extraGenes')}
          </p>
          {(profile?.extra_genes ?? []).length === 0 ? (
            <p className="mt-1 text-sm text-slate-500">{t('account.noExtraGenes')}</p>
          ) : (
            <ul className="mt-1 flex flex-wrap gap-2">
              {profile?.extra_genes.map((g) => (
                <li
                  key={g.id}
                  className="rounded-md bg-blue-50 px-2 py-1 font-mono text-xs text-blue-700"
                >
                  {g.slug}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
          >
            {saving ? t('common.loading') : t('common.save')}
          </button>
        </div>
      </form>

      <form
        onSubmit={(e) => void handleChangePassword(e)}
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <KeyRound className="size-4" aria-hidden="true" />
          {t('account.changePassword')}
        </h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">
              {t('account.currentPassword')}
            </span>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">{t('account.newPassword')}</span>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              required
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </label>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={passwordBusy}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
          >
            {passwordBusy ? t('common.loading') : t('account.changePassword')}
          </button>
        </div>
      </form>
    </section>
  );
}
