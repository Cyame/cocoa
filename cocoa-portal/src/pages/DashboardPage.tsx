import { AlertCircle, ArrowRight, Building2, Layers, LoaderCircle, UserPlus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError } from '@/lib/api';
import { fetchNamespaces, type NamespaceWithStats } from '@/lib/api/namespaces';
import { fetchOrganization, fetchOrganizationMembers } from '@/lib/api/organizations';
import type { Organization, OrgMember } from '@/lib/types';

const RECENT_NAMESPACE_LIMIT = 5;

export default function DashboardPage() {
  const { t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();

  const [org, setOrg] = useState<Organization | null>(null);
  const [namespaces, setNamespaces] = useState<readonly NamespaceWithStats[]>([]);
  const [members, setMembers] = useState<readonly OrgMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (orgId === undefined) return;
    setIsLoading(true);
    setError(null);
    try {
      // fetchNamespaces relies on the X-Organization-Id header injected by the
      // API layer — the AppShell layout syncs currentOrgId before children mount.
      const [orgData, namespacePage, memberPage] = await Promise.all([
        fetchOrganization(orgId),
        fetchNamespaces(),
        fetchOrganizationMembers(orgId),
      ]);
      setOrg(orgData);
      setNamespaces(namespacePage.items);
      setMembers(memberPage.items);
    } catch (fetchError) {
      setError(fetchError instanceof ApiError ? fetchError.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (orgId === undefined) {
    return null;
  }

  const workspaceCount = namespaces.reduce((sum, ns) => sum + ns.workspace_count, 0);
  const recentNamespaces = namespaces.slice(0, RECENT_NAMESPACE_LIMIT);

  return (
    <section className="mx-auto w-full max-w-4xl p-6 lg:p-8" aria-labelledby="dashboard-title">
      <header className="mb-8 flex items-start gap-4">
        <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white">
          <Building2 className="size-6" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          {isLoading && org === null ? (
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('dashboard.loading')}
            </div>
          ) : (
            <>
              <h1 id="dashboard-title" className="truncate text-2xl font-semibold text-slate-950">
                {org?.name ?? t('dashboard.title')}
              </h1>
              {org !== null ? (
                <p className="mt-1 font-mono text-xs text-slate-500">{org.slug}</p>
              ) : null}
            </>
          )}
        </div>
      </header>

      {error !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md px-2 py-0.5 text-xs font-semibold text-red-700 hover:bg-red-100"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('dashboard.statsNamespaces')}
          </p>
          <p
            className="mt-1 text-2xl font-semibold text-slate-900"
            data-testid="dashboard-stats-ns"
          >
            {namespaces.length}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('dashboard.statsMembers')}
          </p>
          <p
            className="mt-1 text-2xl font-semibold text-slate-900"
            data-testid="dashboard-stats-members"
          >
            {members.length}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('dashboard.statsWorkspaces')}
          </p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">{workspaceCount}</p>
        </div>
      </div>

      <div className="mt-8">
        <h2 className="text-sm font-semibold text-slate-900">{t('dashboard.quickActions')}</h2>
        <div className="mt-3 flex flex-wrap gap-3">
          <Link
            to={`/orgs/${orgId}/namespaces`}
            data-testid="dashboard-cta-namespace"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
          >
            <Layers className="size-4" aria-hidden="true" />
            {t('dashboard.quickCreateNamespace')}
          </Link>
          <Link
            to={`/orgs/${orgId}/members`}
            data-testid="dashboard-cta-members"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50"
          >
            <UserPlus className="size-4" aria-hidden="true" />
            {t('dashboard.quickAddMember')}
          </Link>
        </div>
      </div>

      {!isLoading && namespaces.length === 0 ? (
        <div className="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <Layers className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h3 className="mt-3 text-sm font-semibold text-slate-900">
            {t('dashboard.emptyNamespacesTitle')}
          </h3>
          <p className="mt-1 text-sm text-slate-500">{t('dashboard.emptyNamespacesDetail')}</p>
          <Link
            to={`/orgs/${orgId}/namespaces`}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
          >
            {t('dashboard.quickCreateNamespace')}
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      ) : null}

      {!isLoading && members.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <UserPlus className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h3 className="mt-3 text-sm font-semibold text-slate-900">
            {t('dashboard.emptyMembersTitle')}
          </h3>
          <p className="mt-1 text-sm text-slate-500">{t('dashboard.emptyMembersDetail')}</p>
          <Link
            to={`/orgs/${orgId}/members`}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
          >
            {t('dashboard.quickAddMember')}
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      ) : null}

      {!isLoading && recentNamespaces.length > 0 ? (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-slate-900">
            {t('dashboard.recentNamespacesTitle')}
          </h2>
          <ul className="mt-3 space-y-2">
            {recentNamespaces.map((ns) => (
              <li key={ns.id}>
                <Link
                  to={`/orgs/${orgId}/namespaces/${ns.id}`}
                  data-testid={`dashboard-recent-${ns.slug}`}
                  className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 transition-colors hover:border-blue-300 hover:bg-blue-50/40"
                >
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500">
                    <Layers className="size-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-900">{ns.name}</p>
                    <p className="truncate font-mono text-xs text-slate-400">{ns.slug}</p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-slate-300" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
