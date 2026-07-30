import {
  AlertCircle,
  Building2,
  Cpu,
  FlaskConical,
  LoaderCircle,
  Plus,
  RefreshCw,
  Sparkles,
  Users,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useSearchParams } from 'react-router';
import PromoteModal from '@/components/PromoteModal';
import { ApiError, api } from '@/lib/api';
import { type AiGeneCatalogItem, listAiGenes } from '@/lib/api/aiGenes';
import { fetchBaseClassesPage } from '@/lib/api/baseClasses';
import { listNamespaceContracts, type NamespaceContract } from '@/lib/api/contracts';
import { type EntityDetail, fetchEntity, promoteEntity } from '@/lib/api/entities';
import { listMemberships } from '@/lib/api/instances';
import type { NamespaceWithStats } from '@/lib/api/namespaces';
import { fetchDefaultNamespace } from '@/lib/api/namespaces';
import {
  type CatalogUserGene,
  listPermissionKeys,
  listUserGenes,
  updateUserGene,
} from '@/lib/api/users';
import { createWorkspace, fetchWorkspaces } from '@/lib/api/workspaces';
import { translateBaseClassTag } from '@/lib/baseClassTags';
import { toSlug } from '@/lib/slug';
import type { BaseClass, Entity, Instance, Workspace } from '@/lib/types';
import DebugPage from '@/pages/DebugPage';
import { useEntityModalStore } from '@/stores/entityModalStore';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';
import { useSessionStore } from '@/stores/session';

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
  'instances',
  'genes',
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
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createSlug, setCreateSlug] = useState('');
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [namespaceInstances, setNamespaceInstances] = useState<readonly Instance[]>([]);
  const [promoteTarget, setPromoteTarget] = useState<{
    entityId: string;
    instanceId: string;
  } | null>(null);
  const [promoteEntityDetail, setPromoteEntityDetail] = useState<EntityDetail | null>(null);

  const openOnboarding = useOnboardingModalStore((state) => state.open);
  const openEntityModal = useEntityModalStore((state) => state.open);

  const loadWorkspaceTab = useCallback(async () => {
    const workspacePage = await fetchWorkspaces();
    const summaries = await Promise.all(
      workspacePage.items.map(async (workspace) => {
        const [memberships, instances] = await Promise.all([
          listMemberships(workspace.id, 200, 'user'),
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
      } else if (activeTab === 'instances') {
        const [entityPage, instancePage] = await Promise.all([
          api<OffsetPage<Entity>>('/entities?limit=200'),
          api<OffsetPage<Instance>>('/instances?limit=200'),
        ]);
        setEntities(entityPage.items);
        setNamespaceInstances(instancePage.items);
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

  const slugify = (value: string): string => toSlug(value, 48);

  const handleCreateWorkspace = async () => {
    const name = createName.trim();
    const slug = (createSlug.trim() || slugify(name)).slice(0, 48);
    if (!name || !slug) {
      setCreateError(t('namespaces.workspaceName'));
      return;
    }
    setCreateBusy(true);
    setCreateError(null);
    try {
      await createWorkspace({
        name,
        slug,
        namespace_id: namespace?.id ?? null,
      });
      setCreateOpen(false);
      setCreateName('');
      setCreateSlug('');
      await loadWorkspaceTab();
    } catch (error) {
      setCreateError(error instanceof ApiError ? error.message : t('errors.network'));
    } finally {
      setCreateBusy(false);
    }
  };

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
        <div className="flex flex-wrap items-center gap-2">
          {activeTab === 'debug' ? (
            <button
              type="button"
              onClick={() => void refresh()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className="size-4" aria-hidden="true" />
              {t('common.retry')}
            </button>
          ) : null}
          {activeTab === 'workspace' ? (
            <button
              type="button"
              onClick={() => {
                setCreateOpen(true);
                setCreateError(null);
              }}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              <Plus className="size-4" aria-hidden="true" />
              {t('namespaces.createWorkspace')}
            </button>
          ) : null}
          {activeTab === 'base-classes' || activeTab === 'entities' ? (
            <button
              type="button"
              onClick={() => openOnboarding()}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              <Sparkles className="size-4" aria-hidden="true" />
              {t('namespaces.summonEntity')}
            </button>
          ) : null}
          {activeTab === 'entities' ? (
            <button
              type="button"
              disabled={selectedEntityId === null}
              onClick={() => {
                if (selectedEntityId) openEntityModal(selectedEntityId, 'distill');
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            >
              <FlaskConical className="size-4" aria-hidden="true" />
              {t('namespaces.transmute')}
            </button>
          ) : null}
          {activeTab === 'instances' ? (
            <Link
              to="/namespaces?tab=workspace"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
              data-testid="namespaces-go-introduce"
            >
              <Plus className="size-4" aria-hidden="true" />
              {t('namespaces.goIntroduceInWorkspace')}
            </Link>
          ) : null}
          {activeTab === 'genes' ? (
            <button
              type="button"
              disabled
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-400"
            >
              {t('namespaces.genesPack')}
            </button>
          ) : null}
          {activeTab === 'capability-market' ? (
            <>
              <button
                type="button"
                disabled
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white opacity-50"
              >
                {t('namespaces.capabilityCreate')}
              </button>
              <button
                type="button"
                disabled
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-400"
              >
                {t('namespaces.capabilityDistill')}
              </button>
            </>
          ) : null}
        </div>
      </header>

      {createOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-workspace-title"
          className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="create-workspace-title" className="text-base font-semibold text-slate-950">
                {t('namespaces.createWorkspaceTitle')}
              </h2>
              <p className="mt-1 text-sm text-slate-500">{t('namespaces.createWorkspaceHint')}</p>
            </div>
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label={t('namespaces.cancel')}
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('namespaces.workspaceName')}
              </span>
              <input
                value={createName}
                onChange={(event) => {
                  const next = event.target.value;
                  setCreateName(next);
                  if (!createSlug || createSlug === slugify(createName)) {
                    setCreateSlug(slugify(next));
                  }
                }}
                placeholder={t('namespaces.workspaceNamePlaceholder')}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-slate-700">
                {t('namespaces.workspaceSlug')}
              </span>
              <input
                value={createSlug}
                onChange={(event) => setCreateSlug(slugify(event.target.value))}
                placeholder={t('namespaces.workspaceSlugPlaceholder')}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
            </label>
          </div>
          {createError !== null ? (
            <p role="alert" className="mt-3 text-sm text-red-600">
              {createError}
            </p>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {t('namespaces.cancel')}
            </button>
            <button
              type="button"
              disabled={createBusy}
              onClick={() => void handleCreateWorkspace()}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
            >
              {createBusy ? t('namespaces.creatingWorkspace') : t('namespaces.confirmCreate')}
            </button>
          </div>
        </div>
      ) : null}

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
        <WorkspaceTab
          workspaces={workspaces}
          onCreate={() => {
            setCreateOpen(true);
            setCreateError(null);
          }}
          t={t}
        />
      ) : null}

      {!isLoading && activeTab === 'base-classes' ? (
        <BaseClassesTab
          baseClasses={baseClasses.filter(
            (bc) =>
              bc.slug !== 'cerebellum-baseclass' &&
              !(bc.tags ?? []).some((tag) => tag === 'internal' || tag === 'system'),
          )}
          onSummon={(slug) => openOnboarding({ baseClassSlug: slug })}
          t={t}
        />
      ) : null}

      {!isLoading && activeTab === 'contracts' && namespace !== null ? (
        <ContractsTab namespaceId={namespace.id} t={t} />
      ) : null}

      {!isLoading && activeTab === 'entities' ? (
        <EntitiesTab
          entities={entities}
          selectedId={selectedEntityId}
          onSelect={setSelectedEntityId}
          onOpen={(id) => openEntityModal(id)}
          onOpenDistill={(id) => openEntityModal(id, 'distill')}
          t={t}
        />
      ) : null}

      {!isLoading && activeTab === 'instances' ? (
        <NamespaceInstancesTab
          instances={namespaceInstances}
          entities={entities}
          onOpenEntity={(id) => openEntityModal(id, 'instances')}
          onPromote={async (entityId, instanceId) => {
            setPromoteTarget({ entityId, instanceId });
            try {
              const detail = await fetchEntity(entityId);
              setPromoteEntityDetail(detail);
            } catch (error) {
              setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
              setPromoteTarget(null);
            }
          }}
          t={t}
        />
      ) : null}
      {!isLoading && activeTab === 'genes' ? <GenesTab t={t} /> : null}

      {!isLoading && activeTab === 'capability-market' ? <CapabilityMarketTab t={t} /> : null}

      {activeTab === 'debug' ? <DebugPage embedded /> : null}

      {promoteTarget !== null && promoteEntityDetail !== null ? (
        <PromoteModal
          entity={promoteEntityDetail}
          fromInstanceId={promoteTarget.instanceId}
          onClose={() => {
            setPromoteTarget(null);
            setPromoteEntityDetail(null);
          }}
          onSubmit={async (payload) => {
            await promoteEntity(promoteTarget.entityId, {
              ...payload,
              from_instance_id: promoteTarget.instanceId,
            });
            setPromoteTarget(null);
            setPromoteEntityDetail(null);
            void refresh();
          }}
        />
      ) : null}
    </section>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function WorkspaceTab({
  workspaces,
  onCreate,
  t,
}: {
  readonly workspaces: readonly WorkspaceSummary[];
  readonly onCreate: () => void;
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
        <button
          type="button"
          onClick={onCreate}
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
        >
          <Plus className="size-4" aria-hidden="true" />
          {t('namespaces.createWorkspace')}
        </button>
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
              {memberCount} {t('workspace.directors')}
            </span>
            <span className="flex items-center gap-2">
              <Cpu className="size-4 text-slate-400" aria-hidden="true" />
              {instanceCount} {t('workspace.lostOnes')}
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
  readonly onSummon: (slug: string) => void;
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
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(bc.tags ?? []).map((tag) => (
              <span
                key={tag}
                className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600"
              >
                {translateBaseClassTag(tag, t)}
              </span>
            ))}
          </div>
          <button
            type="button"
            onClick={() => onSummon(bc.slug)}
            className="mt-4 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            {t('namespaces.summonFromBaseClass')}
          </button>
        </article>
      ))}
    </div>
  );
}

function ContractsTab({
  namespaceId,
  t,
}: {
  readonly namespaceId: string;
  readonly t: TFn;
}) {
  const [contracts, setContracts] = useState<readonly NamespaceContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void listNamespaceContracts(namespaceId)
      .then((page) => {
        if (!cancelled) setContracts(page.items);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : t('errors.network'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [namespaceId, t]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  if (error !== null) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-sm text-red-800">
        {error}
      </div>
    );
  }

  if (contracts.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <Users className="mx-auto size-8 text-slate-400" aria-hidden="true" />
        <h2 className="mt-4 text-base font-semibold text-slate-900">
          {t('namespaces.contractsTitle')}
        </h2>
        <p className="mt-2 text-sm text-slate-500">{t('namespaces.contractsEmpty')}</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">{t('namespaces.contractsTitle')}</h2>
        <p className="mt-0.5 text-xs text-slate-500">{t('namespaces.contractsDetail')}</p>
      </div>
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">{t('namespaces.contractsUser')}</th>
            <th className="px-4 py-3">{t('namespaces.contractsRole')}</th>
            <th className="px-4 py-3">{t('namespaces.contractsJoined')}</th>
          </tr>
        </thead>
        <tbody>
          {contracts.map((c) => (
            <tr key={c.id} className="border-b border-slate-100 last:border-0">
              <td className="px-4 py-3 font-mono text-xs text-slate-700">{c.user_id}</td>
              <td className="px-4 py-3 capitalize text-slate-600">{c.role}</td>
              <td className="px-4 py-3 text-slate-500">
                {new Date(c.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EntitiesTab({
  entities,
  selectedId,
  onSelect,
  onOpen,
  onOpenDistill,
  t,
}: {
  readonly entities: readonly Entity[];
  readonly selectedId: string | null;
  readonly onSelect: (id: string) => void;
  readonly onOpen: (id: string) => void;
  readonly onOpenDistill: (id: string) => void;
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
            <th className="px-4 py-3">{t('namespaces.entityActions')}</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((entity) => (
            <tr
              key={entity.id}
              className={`border-b border-slate-100 last:border-0 ${
                selectedId === entity.id ? 'bg-blue-50' : ''
              }`}
              onClick={() => onSelect(entity.id)}
            >
              <td className="px-4 py-3 font-medium text-slate-900">
                {entity.display_name ?? entity.name}
              </td>
              <td className="px-4 py-3 font-mono text-xs text-slate-500">{entity.slug}</td>
              <td className="px-4 py-3 capitalize text-slate-600">{entity.rank}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpen(entity.id);
                    }}
                    className="text-blue-600 hover:text-blue-700"
                  >
                    {t('namespaces.viewDetail')}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenDistill(entity.id);
                    }}
                    className="inline-flex items-center gap-1 text-purple-700 hover:text-purple-800"
                    data-testid={`entity-transmute-${entity.id}`}
                  >
                    <FlaskConical className="size-3.5" aria-hidden="true" />
                    {t('transmuteModal.open')}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NamespaceInstancesTab({
  instances,
  entities,
  onOpenEntity,
  onPromote,
  t,
}: {
  readonly instances: readonly Instance[];
  readonly entities: readonly Entity[];
  readonly onOpenEntity: (entityId: string) => void;
  readonly onPromote: (entityId: string, instanceId: string) => void;
  readonly t: TFn;
}) {
  const entityById = new Map(entities.map((e) => [e.id, e]));

  if (instances.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <Cpu className="mx-auto size-8 text-slate-400" aria-hidden="true" />
        <h2 className="mt-4 text-base font-semibold text-slate-900">
          {t('namespaces.instancesTitle')}
        </h2>
        <p className="mt-2 text-sm text-slate-500">{t('namespaces.instancesEmpty')}</p>
        <Link
          to="/namespaces?tab=workspace"
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
        >
          {t('namespaces.goIntroduceInWorkspace')}
        </Link>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">{t('namespaces.instanceEntity')}</th>
            <th className="px-4 py-3">{t('namespaces.instanceId')}</th>
            <th className="px-4 py-3">{t('namespaces.instanceStatus')}</th>
            <th className="px-4 py-3">{t('namespaces.entityActions')}</th>
          </tr>
        </thead>
        <tbody>
          {instances.map((inst) => {
            const entity = entityById.get(inst.entity_id);
            const label = entity?.display_name ?? entity?.name ?? inst.entity_id;
            return (
              <tr key={inst.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-900">{label}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  {inst.id.slice(0, 8)}
                </td>
                <td className="px-4 py-3 capitalize text-slate-600">{inst.status}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onOpenEntity(inst.entity_id)}
                      className="text-blue-600 hover:text-blue-700"
                    >
                      {t('namespaces.viewDetail')}
                    </button>
                    <button
                      type="button"
                      onClick={() => onPromote(inst.entity_id, inst.id)}
                      className="inline-flex items-center gap-1 text-emerald-700 hover:text-emerald-800"
                      data-testid={`instance-promote-${inst.id}`}
                    >
                      <Sparkles className="size-3.5" aria-hidden="true" />
                      {t('promoteModal.open')}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function GenesTab({ t }: { readonly t: TFn }) {
  const [subTab, setSubTab] = useState<'deep-sea' | 'human'>('deep-sea');

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label={t('nav.genes')}
        className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1"
        data-testid="genes-subtabs"
      >
        {(
          [
            { id: 'deep-sea' as const, label: t('namespaces.genesSubDeepSea') },
            { id: 'human' as const, label: t('namespaces.genesSubHuman') },
          ] as const
        ).map((tab) => {
          const active = subTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active}
              data-testid={`genes-subtab-${tab.id}`}
              onClick={() => setSubTab(tab.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                active
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:bg-white hover:text-slate-900'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {subTab === 'deep-sea' ? <DeepSeaGenesPanel t={t} /> : <HumanGenesPanel t={t} />}
    </div>
  );
}

function DeepSeaGenesPanel({ t }: { readonly t: TFn }) {
  const [genes, setGenes] = useState<readonly AiGeneCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const page = await listAiGenes();
      setGenes(page.items);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-900">{t('namespaces.aiGenesTitle')}</h2>
        <p className="mt-1 text-sm text-slate-500">{t('namespaces.aiGenesDetail')}</p>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      ) : null}
      {genes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          {t('namespaces.aiGenesEmpty')}
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm" data-testid="ai-genes-table">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">{t('entityModal.fields.displayName')}</th>
                <th className="px-4 py-3">{t('entityModal.fields.slug')}</th>
                <th className="px-4 py-3">{t('namespaces.aiGenesTags')}</th>
              </tr>
            </thead>
            <tbody>
              {genes.map((gene) => (
                <tr key={gene.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{gene.name}</p>
                    {gene.description ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">
                        {gene.description}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{gene.slug}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(gene.tags ?? []).length === 0 ? (
                        <span className="text-xs text-slate-400">—</span>
                      ) : (
                        (gene.tags ?? []).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600"
                          >
                            {tag}
                          </span>
                        ))
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function HumanGenesPanel({ t }: { readonly t: TFn }) {
  const user = useSessionStore((state) => state.user);
  const canWrite = user?.is_super_admin === true || user?.identity === 'system';
  const [genes, setGenes] = useState<readonly CatalogUserGene[]>([]);
  const [permissionKeys, setPermissionKeys] = useState<readonly string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftKeys, setDraftKeys] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [genePage, keys] = await Promise.all([listUserGenes(), listPermissionKeys()]);
      setGenes(genePage.items);
      setPermissionKeys(keys);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(gene: CatalogUserGene) {
    setEditingId(gene.id);
    setDraftKeys(new Set(gene.permission_keys ?? []));
    setNotice(null);
  }

  async function saveEdit(geneId: string) {
    setBusy(true);
    setErrorMessage(null);
    try {
      await updateUserGene(geneId, { permission_keys: Array.from(draftKeys) });
      setEditingId(null);
      setNotice(t('namespaces.genesSaved'));
      await load();
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        {t('common.loading')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-900">{t('namespaces.genesTitle')}</h2>
        <p className="mt-1 text-sm text-slate-500">{t('namespaces.genesDetail')}</p>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="text-sm text-emerald-700">
          {notice}
        </p>
      ) : null}
      {genes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          {t('namespaces.genesEmpty')}
        </p>
      ) : (
        <div className="space-y-3">
          {genes.map((gene) => {
            const editing = editingId === gene.id;
            const isIdentity = gene.slug.startsWith('identity-');
            return (
              <article
                key={gene.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-slate-900">{gene.name}</p>
                    <p className="font-mono text-xs text-slate-500">{gene.slug}</p>
                    {gene.description ? (
                      <p className="mt-1 text-xs text-slate-500">{gene.description}</p>
                    ) : null}
                  </div>
                  {canWrite ? (
                    editing ? (
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="rounded-md border border-slate-200 px-2 py-1 text-xs"
                        >
                          {t('common.cancel')}
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void saveEdit(gene.id)}
                          className="rounded-md bg-blue-600 px-2 py-1 text-xs font-semibold text-white disabled:opacity-60"
                        >
                          {t('common.save')}
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startEdit(gene)}
                        className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                      >
                        {t('namespaces.genesEdit')}
                      </button>
                    )
                  ) : null}
                </div>
                <div className="mt-3">
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {t('namespaces.genesPermissions')}
                    {isIdentity ? (
                      <span className="ml-2 font-normal normal-case tracking-normal text-slate-400">
                        (identity)
                      </span>
                    ) : null}
                  </p>
                  {editing ? (
                    <div className="grid max-h-48 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                      {permissionKeys.map((key) => (
                        <label
                          key={key}
                          className="flex items-center gap-2 rounded-md px-2 py-1 font-mono text-xs hover:bg-slate-50"
                        >
                          <input
                            type="checkbox"
                            checked={draftKeys.has(key)}
                            onChange={(e) => {
                              setDraftKeys((prev) => {
                                const next = new Set(prev);
                                if (e.target.checked) next.add(key);
                                else next.delete(key);
                                return next;
                              });
                            }}
                            className="size-3.5 accent-blue-600"
                          />
                          {key}
                        </label>
                      ))}
                    </div>
                  ) : (
                    <p className="font-mono text-xs text-slate-700">
                      {(gene.permission_keys ?? []).join(', ') || '—'}
                    </p>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
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
