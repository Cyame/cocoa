import { AlertCircle, Copy, LoaderCircle, Settings } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import { fetchMe } from '@/lib/api/auth';
import { cloneOrganization } from '@/lib/api/clone';
import { fetchOrganization } from '@/lib/api/organizations';
import type { Organization, OrgIdentity } from '@/lib/types';
import { cn } from '@/lib/utils';
import { OrganizationProvidersPanel } from '@/pages/organization/OrganizationProvidersPanel';
import { OrganizationWorldPanel } from '@/pages/organization/OrganizationWorldPanels';
import { useSessionStore } from '@/stores/session';

export default function WorldSettingsPage() {
  const { t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const user = useSessionStore((state) => state.user);
  const isSuperAdmin = user?.is_super_admin ?? false;
  // H7: tenant gating reads org_identity.atoms from GET /auth/me (same pattern
  // as StatusBar). The legacy `identity` field never yields 'org', so org
  // managers holding can_manage_organization were locked out before.
  const [orgIdentity, setOrgIdentity] = useState<OrgIdentity | null>(null);
  const canManageWorld =
    isSuperAdmin || (orgIdentity?.atoms.includes('can_manage_organization') ?? false);
  const canCloneWorld =
    isSuperAdmin || (orgIdentity?.atoms.includes('can_clone_organization') ?? false);

  useEffect(() => {
    if (orgId === undefined) {
      setOrgIdentity(null);
      return;
    }
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (!cancelled) setOrgIdentity(me.org_identity ?? null);
      })
      .catch(() => {
        if (!cancelled) setOrgIdentity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  const [org, setOrg] = useState<Organization | null>(null);
  const [useProxy, setUseProxy] = useState(false);
  const [proxyHost, setProxyHost] = useState('');
  const [proxyPort, setProxyPort] = useState('');
  const [proxyUsername, setProxyUsername] = useState('');
  const [proxyPassword, setProxyPassword] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (orgId === undefined) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchOrganization(orgId);
      setOrg(data);
      setUseProxy(data.use_proxy);
      setProxyHost(data.proxy_host ?? '');
      setProxyPort(data.proxy_port !== null ? String(data.proxy_port) : '');
      setProxyUsername(data.proxy_username ?? '');
      setProxyPassword(data.proxy_password ?? '');
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCloneWorld() {
    if (!canCloneWorld || orgId === undefined || org === null) return;
    const ok = window.confirm(t('clone.confirmOrganization', { name: org.name }));
    if (!ok) return;
    setBusy(true);
    setErrorMessage(null);
    setNotice(null);
    try {
      await cloneOrganization(orgId);
      navigate('/orgs/picker');
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('clone.error'));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveProxy() {
    if (!canManageWorld || orgId === undefined) return;
    setBusy(true);
    setErrorMessage(null);
    setNotice(null);
    try {
      const next = await api<Organization>(`/organizations/${encodeURIComponent(orgId)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          use_proxy: useProxy,
          proxy_host: proxyHost.trim() || null,
          proxy_port: proxyPort.trim() ? Number(proxyPort.trim()) : null,
          proxy_username: proxyUsername.trim() || null,
          proxy_password: proxyPassword.trim() || null,
        }),
      });
      setOrg(next);
      setNotice(t('organization.world.saved'));
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  }

  if (orgId === undefined) {
    return null;
  }

  return (
    <section className="mx-auto w-full max-w-5xl p-6 lg:p-8" aria-labelledby="settings-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Settings className="size-6" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          {isLoading && org === null ? (
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('common.loading')}
            </div>
          ) : (
            <>
              <h1 id="settings-title" className="truncate text-2xl font-semibold text-slate-950">
                {t('nav.settings')}
              </h1>
              {org !== null ? (
                <p className="mt-1 text-sm text-slate-500">
                  {org.name} <span className="font-mono text-xs">({org.slug})</span>
                </p>
              ) : null}
            </>
          )}
        </div>
        {!canManageWorld ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {t('organization.readOnlyHint')}
          </p>
        ) : null}
      </header>

      {errorMessage !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      <div className="space-y-6">
        <OrganizationWorldPanel canWrite={canManageWorld} orgId={orgId} />

        {org !== null ? (
          <section className="max-w-xl space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">
              {t('settings.proxyTitle', { defaultValue: 'Egress proxy' })}
            </h2>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={useProxy}
                disabled={!canManageWorld}
                onChange={(e) => setUseProxy(e.target.checked)}
                className="size-4 accent-blue-600"
              />
              {t('settings.useProxy', { defaultValue: 'Route outbound requests through a proxy' })}
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('settings.proxyHost', { defaultValue: 'Host' })}
                </span>
                <input
                  value={proxyHost}
                  disabled={!canManageWorld || !useProxy}
                  onChange={(e) => setProxyHost(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm disabled:bg-slate-50"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('settings.proxyPort', { defaultValue: 'Port' })}
                </span>
                <input
                  value={proxyPort}
                  disabled={!canManageWorld || !useProxy}
                  onChange={(e) => setProxyPort(e.target.value)}
                  inputMode="numeric"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm disabled:bg-slate-50"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('settings.proxyUsername', { defaultValue: 'Username' })}
                </span>
                <input
                  value={proxyUsername}
                  disabled={!canManageWorld || !useProxy}
                  onChange={(e) => setProxyUsername(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:bg-slate-50"
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-slate-700">
                  {t('settings.proxyPassword', { defaultValue: 'Password' })}
                </span>
                <input
                  type="password"
                  value={proxyPassword}
                  disabled={!canManageWorld || !useProxy}
                  onChange={(e) => setProxyPassword(e.target.value)}
                  autoComplete="off"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:bg-slate-50"
                />
              </label>
            </div>
            {notice !== null ? (
              <p role="status" className="text-sm text-emerald-700">
                {notice}
              </p>
            ) : null}
            {canManageWorld ? (
              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={busy || (useProxy && proxyHost.trim().length === 0)}
                  onClick={() => void handleSaveProxy()}
                  className={cn(
                    'rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white',
                    'disabled:opacity-60',
                  )}
                >
                  {t('common.save')}
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        <OrganizationProvidersPanel canWrite={canManageWorld} orgId={orgId} />

        {canCloneWorld && org !== null ? (
          <section className="max-w-xl space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">{t('clone.organization')}</h2>
            <p className="text-sm text-slate-500">{t('clone.instancesNotCopied')}</p>
            <div className="flex justify-end">
              <button
                type="button"
                disabled={busy}
                onClick={() => void handleCloneWorld()}
                data-testid="clone-organization"
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white',
                  'px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50',
                  'disabled:opacity-60',
                )}
              >
                <Copy className="size-4" aria-hidden="true" />
                {busy ? t('clone.cloning') : t('clone.organization')}
              </button>
            </div>
          </section>
        ) : null}
      </div>
    </section>
  );
}
