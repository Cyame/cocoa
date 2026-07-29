import {
  AlertCircle,
  Building2,
  Cpu,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Users,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useSearchParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import { fetchBaseClassesPage } from '@/lib/api/baseClasses';
import type { NamespaceWithStats } from '@/lib/api/namespaces';
import { fetchDefaultNamespace } from '@/lib/api/namespaces';
import { fetchWorkspaces } from '@/lib/api/workspaces';
import type { BaseClass, Entity, Workspace } from '@/lib/types';
import DebugPage from '@/pages/DebugPage';
import { useEntityModalStore } from '@/stores/entityModalStore';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

type WorkspaceSummary = {
  readonly workspace: Workspace;
  readonly memberCount: number;
  readonly instanceCount: number;
};

type CountPage = {
  readonly items: readonly { readonly id: string }[];
  readonly total: number;
};

const VALID_TABS = new Set([
  'workspace',
  'base-classes',
  'contracts',
  'entities',
  'capability-market',
  'debug',
]);

export default function NamespacesPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const rawTab = searchParams.get('tab') ?? 'workspace';
  const activeTab = VALID_TABS.has(rawTab) ? rawTab : 'workspace';

  const [namespace, setNamespace] = useState<NamespaceWithStats | null>(null);
  const [workspaces, setWorkspaces] = useState<readonly WorkspaceSummary[]>([]);
  const [baseClasses, setBaseClasses] = useState<readonly BaseClass[]>([]);
  const [entities, setEntities] = useState<readonly Entity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const openOnboarding = useOnboardingModalStore((state) => state.open);
  const openEntityModal = useEntityModalStore((state) => state.open);

  const loadWorkspaceTab = useCallback(async () => {
    const workspacePage = await fetchWorkspaces();
    const summaries = await Promise.all(
      workspacePage.items.map(async (workspace) => {
        const [memberships, instances] = await Promise.all([
          api<CountPage>(`/messaging/memberships?workspace_id=${encodeURIComponent(workspace.id)}`),
          api<CountPage>(`/instances?workspace_id=${encodeURIComponent(workspace.id)}`),
        ]);
        return {
          workspace,
          memberCount: memberships.total,
          instanceCount: instances.total,
        } satisfies WorkspaceSummary;
      }),
    );
    setWorkspaces(summaries);
  }, []);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const ns = await fetchDefaultNamespace();
      setNamespace(ns);

      if (activeTab === 'workspace') {
        await loadWorkspaceTab();
      } else if (activeTab === 'base-classes') {
        const page = await fetchBaseClassesPage({ limit: 50, offset: 0 });
        setBaseClasses(page.items);
      } else if (activeTab === 'entities') {
        const page = await api<OffsetPage<Entity>>('/entities?limit=200');
        setEntities(page.items);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) {
          setIsUnauthorized(true);
          return;
        }
        setErrorMessage(error.message);
        return;
      }
      setErrorMessage(t('errors.network'));
    } finally {
      setIsLoading(false);
    }
  }, [activeTab, loadWorkspaceTab, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (isUnauthorized) {
    return <Navigate to="/login" replace />;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="namespaces-title">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div>
            <h1
              id="namespaces-title"
              className="text-2xl font-semibold tracking-tight text-slate-950"
            >
              {namespace?.name ?? t('namespaces.title')}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              {namespace?.description ?? t('namespaces.subtitle')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            {t('common.retry')}
          </button>
          <button
            type="button"
            onClick={openOnboarding}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          >
            <Sparkles className="size-4" aria-hidden="true" />
            {t('namespaces.summonEntity')}
          </button>
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

      {isLoading && activeTab !== 'debug' ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {!isLoading && activeTab === 'workspace' ? (
        <WorkspaceTab workspaces={workspaces} t={t} />
      ) : null}

      {!isLoading && activeTab === 'base-classes' ? (
        <BaseClassesTab baseClasses={baseClasses} onSummon={openOnboarding} t={t} />
      ) : null}

      {!isLoading && activeTab === 'contracts' ? <ContractsTab t={t} /> : null}

      {!isLoading && activeTab === 'entities' ? (
        <EntitiesTab entities={entities} onOpen={openEntityModal} t={t} />
      ) : null}

      {!isLoading && activeTab === 'capability-market' ? <CapabilityMarketTab t={t} /> : null}

      {activeTab === 'debug' ? <DebugPage embedded /> : null}
    </section>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function WorkspaceTab({
  workspaces,
  t,
}: {
  readonly workspaces: readonly WorkspaceSummary[];
  readonly t: TFn;
}) {
  if (workspaces.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <Building2 className="mx-auto size-8 text-slate-400" aria-hidden="true" />
        <h2 className="mt-4 text-base font-semibold text-slate-900">
          {t('namespaces.noWorkspacesTitle')}
        </h2>
        <p className="mt-2 text-sm text-slate-500">{t('namespaces.noWorkspacesDetail')}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {workspaces.map(({ workspace, memberCount, instanceCount }) => (
        <Link
          key={workspace.id}
          to={`/workspaces/${workspace.id}`}
          className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md"
        >
          <div className="flex items-start justify-between gap-4">
            <span className="grid size-10 place-items-center rounded-lg bg-blue-50 text-blue-700 group-hover:bg-blue-100">
              <Building2 className="size-5" aria-hidden="true" />
            </span>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-mono text-xs text-slate-600">
              {workspace.slug}
            </span>
          </div>
          <h2 className="mt-5 text-lg font-semibold tracking-tight text-slate-950">
            {workspace.name}
          </h2>
          <div className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm text-slate-600">
            <span className="flex items-center gap-2">
              <Users className="size-4 text-slate-400" aria-hidden="true" />
              {memberCount} {t('workspace.members')}
            </span>
            <span className="flex items-center gap-2">
              <Cpu className="size-4 text-slate-400" aria-hidden="true" />
              {instanceCount} {t('workspace.instances')}
            </span>
          </div>
          <p className="mt-4 text-sm font-medium text-blue-600">{t('namespaces.enterWorkspace')}</p>
        </Link>
      ))}
    </div>
  );
}

function BaseClassesTab({
  baseClasses,
  onSummon,
  t,
}: {
  readonly baseClasses: readonly BaseClass[];
  readonly onSummon: () => void;
  readonly t: TFn;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {baseClasses.map((bc) => (
        <article key={bc.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <Link to={`/base-classes/${bc.slug}`} className="block">
            <h2 className="text-lg font-semibold text-slate-950">{bc.display_name ?? bc.name}</h2>
            <p className="mt-1 font-mono text-xs text-slate-500">{bc.slug}</p>
            <p className="mt-3 line-clamp-3 text-sm text-slate-600">{bc.description}</p>
          </Link>
          <button
            type="button"
            onClick={onSummon}
            className="mt-4 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            {t('namespaces.summonFromBaseClass')}
          </button>
        </article>
      ))}
    </div>
  );
}

function ContractsTab({ t }: { readonly t: TFn }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
      <Users className="mx-auto size-8 text-slate-400" aria-hidden="true" />
      <h2 className="mt-4 text-base font-semibold text-slate-900">
        {t('namespaces.contractsTitle')}
      </h2>
      <p className="mt-2 text-sm text-slate-500">{t('namespaces.contractsDetail')}</p>
    </div>
  );
}

function EntitiesTab({
  entities,
  onOpen,
  t,
}: {
  readonly entities: readonly Entity[];
  readonly onOpen: (id: string) => void;
  readonly t: TFn;
}) {
  if (entities.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <p className="text-sm text-slate-500">{t('namespaces.noEntities')}</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">{t('entityModal.fields.displayName')}</th>
            <th className="px-4 py-3">{t('entityModal.fields.slug')}</th>
            <th className="px-4 py-3">{t('entityModal.fields.rank')}</th>
            <th className="px-4 py-3">{t('common.confirm')}</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((entity) => (
            <tr key={entity.id} className="border-b border-slate-100 last:border-0">
              <td className="px-4 py-3 font-medium text-slate-900">
                {entity.display_name ?? entity.name}
              </td>
              <td className="px-4 py-3 font-mono text-xs text-slate-500">{entity.slug}</td>
              <td className="px-4 py-3 capitalize text-slate-600">{entity.rank}</td>
              <td className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => onOpen(entity.id)}
                  className="text-blue-600 hover:text-blue-700"
                >
                  {t('namespaces.viewDetail')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CapabilityMarketTab({ t }: { readonly t: TFn }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
      <Sparkles className="mx-auto size-8 text-slate-400" aria-hidden="true" />
      <h2 className="mt-4 text-base font-semibold text-slate-900">
        {t('namespaces.capabilityMarketTitle')}
      </h2>
      <p className="mt-2 text-sm text-slate-500">{t('namespaces.capabilityMarketDetail')}</p>
    </div>
  );
}
