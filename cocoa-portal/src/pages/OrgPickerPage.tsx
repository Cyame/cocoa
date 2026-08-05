import { AlertCircle, Building2, LoaderCircle, Plus, UserRound } from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useNavigate } from 'react-router';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { ApiError } from '@/lib/api';
import { createOrganization, fetchOrganizations } from '@/lib/api/organizations';
import type { Organization } from '@/lib/types';
import { useSessionStore } from '@/stores/session';

const SLUG_PATTERN = /^[a-z][a-z0-9-]*$/;

export default function OrgPickerPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const token = useSessionStore((state) => state.token);
  const setCurrentOrg = useSessionStore((state) => state.setCurrentOrg);

  const [orgs, setOrgs] = useState<readonly Organization[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (token === null) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      // v4.3+ GET /organizations is an OffsetPage — unwrap `.items`.
      const page = await fetchOrganizations();
      if (!Array.isArray(page.items)) {
        // Runtime guard: never white-screen on a malformed list payload.
        setLoadError(t('errors.invalidResponse'));
        return;
      }
      setOrgs(page.items);
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [token, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (token === null) {
    return <Navigate to="/login" replace />;
  }

  function openCreate() {
    setShowCreate(true);
    setCreateError(null);
  }

  function handleSelect(orgId: string) {
    setCurrentOrg(orgId);
    navigate(`/orgs/${orgId}`);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedSlug = slug.trim();
    if (trimmedName.length === 0) {
      setCreateError(t('orgPicker.nameRequired'));
      return;
    }
    if (!SLUG_PATTERN.test(trimmedSlug)) {
      setCreateError(t('orgPicker.slugPattern'));
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createOrganization({
        name: trimmedName,
        slug: trimmedSlug,
        description: description.trim().length > 0 ? description.trim() : null,
      });
      // H1: self-created org auto-selects and lands on its Dashboard — never
      // bounce back through the picker.
      setCurrentOrg(created.id);
      navigate(`/orgs/${created.id}`, { replace: true });
    } catch (error) {
      setCreateError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-slate-950 px-4 py-10 text-slate-100">
      <section className="w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl shadow-black/30 sm:p-8">
        <div className="mb-8 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
              <Building2 className="size-6" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold tracking-tight">{t('common.appName')}</p>
              <p className="text-xs text-slate-400">{t('common.appTagline')}</p>
            </div>
          </div>
          <LanguageSwitcher variant="sidebar" placement="down" />
        </div>

        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">{t('orgPicker.title')}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">{t('orgPicker.subtitle')}</p>
        </div>

        {loadError !== null ? (
          <div
            role="alert"
            className="mb-5 flex gap-3 rounded-lg border border-red-800/80 bg-red-950/70 px-4 py-3 text-sm text-red-200"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p className="flex-1">{loadError}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="rounded-md px-2 py-0.5 text-xs font-semibold text-red-200 hover:bg-red-900/60"
            >
              {t('common.retry')}
            </button>
          </div>
        ) : null}

        {isLoading ? (
          <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-400">
            <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
            {t('orgPicker.loading')}
          </div>
        ) : orgs === null ? null : orgs.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-6 py-12 text-center">
            <UserRound className="mx-auto size-8 text-slate-500" aria-hidden="true" />
            <h2 className="mt-4 text-sm font-semibold text-slate-200">
              {t('orgPicker.emptyTitle')}
            </h2>
            <p className="mt-2 text-sm text-slate-400">{t('orgPicker.emptyDetail')}</p>
            <button
              type="button"
              onClick={openCreate}
              data-testid="org-picker-empty-cta"
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
            >
              <Plus className="size-4" aria-hidden="true" />
              {t('orgPicker.ctaCreate')}
            </button>
          </div>
        ) : (
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200">{t('orgPicker.listTitle')}</h2>
              <button
                type="button"
                onClick={openCreate}
                data-testid="org-picker-create"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-800"
              >
                <Plus className="size-3.5" aria-hidden="true" />
                {t('orgPicker.ctaCreate')}
              </button>
            </div>
            <ul className="grid gap-3 sm:grid-cols-2">
              {orgs.map((org) => (
                <li key={org.id}>
                  <button
                    type="button"
                    onClick={() => handleSelect(org.id)}
                    data-testid={`org-card-${org.slug}`}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-left transition-colors hover:border-blue-500/60 hover:bg-slate-900"
                  >
                    <p className="truncate text-sm font-semibold text-slate-100">{org.name}</p>
                    <p className="mt-0.5 truncate font-mono text-xs text-slate-500">{org.slug}</p>
                    {org.description ? (
                      <p className="mt-2 line-clamp-2 text-xs text-slate-400">{org.description}</p>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {showCreate ? (
          <form
            onSubmit={(event) => void handleCreate(event)}
            className="mt-6 space-y-4 rounded-xl border border-slate-700 bg-slate-950/60 p-5"
          >
            <h2 className="text-sm font-semibold text-slate-200">{t('orgPicker.createTitle')}</h2>
            <div>
              <label htmlFor="org-name" className="mb-1.5 block text-sm font-medium text-slate-300">
                {t('orgPicker.name')}
              </label>
              <input
                id="org-name"
                value={name}
                onChange={(event) => setName(event.currentTarget.value)}
                required
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div>
              <label htmlFor="org-slug" className="mb-1.5 block text-sm font-medium text-slate-300">
                {t('orgPicker.slug')}
              </label>
              <input
                id="org-slug"
                value={slug}
                onChange={(event) => setSlug(event.currentTarget.value)}
                placeholder="kebab-case"
                required
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div>
              <label
                htmlFor="org-description"
                className="mb-1.5 block text-sm font-medium text-slate-300"
              >
                {t('orgPicker.description')}
              </label>
              <textarea
                id="org-description"
                value={description}
                onChange={(event) => setDescription(event.currentTarget.value)}
                rows={2}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            {createError !== null ? (
              <p role="alert" className="flex items-center gap-2 text-sm text-red-400">
                <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
                {createError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800"
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                disabled={creating}
                aria-busy={creating}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-wait disabled:opacity-60"
              >
                {creating ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Plus className="size-4" aria-hidden="true" />
                )}
                {t('orgPicker.submitCreate')}
              </button>
            </div>
          </form>
        ) : null}
      </section>
    </main>
  );
}
