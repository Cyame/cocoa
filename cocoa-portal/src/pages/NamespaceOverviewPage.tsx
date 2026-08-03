import {
  AlertCircle,
  ArrowRight,
  Building2,
  Fingerprint,
  Layers,
  LoaderCircle,
  Users,
  Workflow,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type { NamespaceWithStats } from '@/lib/api/namespaces';

export default function NamespaceOverviewPage() {
  const { t } = useTranslation();
  const { orgId, nsId } = useParams<{ orgId: string; nsId: string }>();

  const [namespace, setNamespace] = useState<NamespaceWithStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (nsId === undefined) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await api<NamespaceWithStats>(`/namespaces/${encodeURIComponent(nsId)}`);
      setNamespace(data);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [nsId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (orgId === undefined || nsId === undefined) {
    return null;
  }

  const subPages = [
    {
      to: `/orgs/${orgId}/namespaces/${nsId}/workspaces`,
      label: t('nav.workspaces'),
      icon: Building2,
    },
    { to: `/orgs/${orgId}/namespaces/${nsId}/entities`, label: t('nav.entities'), icon: Users },
    {
      to: `/orgs/${orgId}/namespaces/${nsId}/instances`,
      label: t('nav.instances'),
      icon: Workflow,
    },
    {
      to: `/orgs/${orgId}/namespaces/${nsId}/contracts`,
      label: t('nav.contracts'),
      icon: Fingerprint,
    },
  ] as const;

  return (
    <section className="mx-auto w-full max-w-4xl p-6 lg:p-8" aria-labelledby="ns-overview-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Layers className="size-6" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          {isLoading && namespace === null ? (
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('common.loading')}
            </div>
          ) : (
            <>
              <h1 id="ns-overview-title" className="truncate text-2xl font-semibold text-slate-950">
                {namespace?.name ?? t('nav.namespaces')}
              </h1>
              <p className="mt-1 font-mono text-xs text-slate-500">{namespace?.slug}</p>
              {namespace?.description ? (
                <p className="mt-2 max-w-2xl text-sm text-slate-600">{namespace.description}</p>
              ) : null}
            </>
          )}
        </div>
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

      {!isLoading && namespace !== null ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {t('nav.workspaces')}
              </p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">
                {namespace.workspace_count}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {t('nav.entities')}
              </p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">{namespace.entity_count}</p>
            </div>
          </div>

          <h2 className="mt-8 text-sm font-semibold text-slate-900">{t('nav.currentNamespace')}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {subPages.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-blue-300 hover:bg-blue-50/40"
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500 group-hover:bg-blue-100 group-hover:text-blue-700">
                  <Icon className="size-5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900">
                  {label}
                </span>
                <ArrowRight className="size-4 shrink-0 text-slate-300" aria-hidden="true" />
              </Link>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
