import { AlertCircle, Building2, Copy, Cpu, LoaderCircle, Plus, Users, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate, useParams } from 'react-router';
import CloneDialog from '@/components/CloneDialog';
import { ApiError, api } from '@/lib/api';
import { fetchMe } from '@/lib/api/auth';
import { type ClonePayload, cloneWorkspace } from '@/lib/api/clone';
import { listMemberships } from '@/lib/api/instances';
import { createWorkspace, fetchWorkspaces } from '@/lib/api/workspaces';
import { toSlug } from '@/lib/slug';
import type { OrgIdentity, Workspace } from '@/lib/types';
import { useSessionStore } from '@/stores/session';

type WorkspaceSummary = {
  readonly workspace: Workspace;
  readonly memberCount: number;
  readonly instanceCount: number;
};

type CountPage = {
  readonly items: readonly { readonly id: string }[];
  readonly total: number;
};

export default function NamespaceWorkspacesPage() {
  const { t } = useTranslation();
  const { orgId, nsId } = useParams<{ orgId: string; nsId: string }>();
  const navigate = useNavigate();
  const user = useSessionStore((state) => state.user);
  const isSuperAdmin = user?.is_super_admin ?? false;
  const [orgIdentity, setOrgIdentity] = useState<OrgIdentity | null>(null);
  const canCloneWorkspace =
    isSuperAdmin || (orgIdentity?.atoms.includes('can_clone_workspace') ?? false);

  const [workspaces, setWorkspaces] = useState<readonly WorkspaceSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [cloningId, setCloningId] = useState<string | null>(null);
  const [cloneTarget, setCloneTarget] = useState<Workspace | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createSlug, setCreateSlug] = useState('');
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

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

  const loadWorkspaces = useCallback(async () => {
    if (nsId === undefined) return;
    const workspacePage = await fetchWorkspaces({ namespace_id: nsId, limit: 50, offset: 0 });
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
  }, [nsId]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      await loadWorkspaces();
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
  }, [loadWorkspaces, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const slugify = (value: string): string => toSlug(value, 48);

  const handleCloneWorkspace = async (workspace: Workspace, payload: ClonePayload) => {
    setCloningId(workspace.id);
    setErrorMessage(null);
    try {
      const cloned = await cloneWorkspace(workspace.id, payload);
      navigate(`/orgs/${orgId ?? ''}/workspaces/${cloned.id}`);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t('clone.error'));
    } finally {
      setCloningId(null);
      setCloneTarget(null);
    }
  };

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
        namespace_id: nsId ?? null,
      });
      setCreateOpen(false);
      setCreateName('');
      setCreateSlug('');
      await loadWorkspaces();
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
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="ns-workspaces-title">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div>
            <h1 id="ns-workspaces-title" className="text-2xl font-semibold text-slate-950">
              {t('nav.workspaces')}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('namespaces.subtitle')}</p>
          </div>
        </div>
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

      {isLoading ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {!isLoading ? (
        <WorkspaceList
          orgId={orgId ?? ''}
          workspaces={workspaces}
          canClone={canCloneWorkspace}
          cloningId={cloningId}
          onClone={(workspace) => setCloneTarget(workspace)}
          onCreate={() => {
            setCreateOpen(true);
            setCreateError(null);
          }}
          t={t}
        />
      ) : null}

      <CloneDialog
        open={cloneTarget !== null}
        title={t('clone.workspace')}
        confirmMessage={t('clone.confirmWorkspace', { name: cloneTarget?.name ?? '' })}
        confirmLabel={t('clone.workspace')}
        busy={cloneTarget !== null && cloningId === cloneTarget.id}
        onConfirm={(payload) => {
          if (cloneTarget !== null) void handleCloneWorkspace(cloneTarget, payload);
        }}
        onCancel={() => setCloneTarget(null)}
      />
    </section>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function WorkspaceList({
  orgId,
  workspaces,
  canClone,
  cloningId,
  onClone,
  onCreate,
  t,
}: {
  readonly orgId: string;
  readonly workspaces: readonly WorkspaceSummary[];
  readonly canClone: boolean;
  readonly cloningId: string | null;
  readonly onClone: (workspace: Workspace) => void;
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
        <div
          key={workspace.id}
          className="group rounded-xl border border-slate-200 bg-white shadow-sm transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md"
        >
          <Link to={`/orgs/${orgId}/workspaces/${workspace.id}`} className="block p-5">
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
            <p className="mt-4 text-sm font-medium text-blue-600">
              {t('namespaces.enterWorkspace')}
            </p>
          </Link>
          <div className="flex justify-end border-t border-slate-100 px-5 py-3">
            {canClone ? (
              <button
                type="button"
                disabled={cloningId !== null}
                onClick={() => onClone(workspace)}
                data-testid={`workspace-clone-${workspace.id}`}
                title={t('clone.instancesNotCopied')}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 disabled:opacity-50"
              >
                <Copy className="size-3.5" aria-hidden="true" />
                {cloningId === workspace.id ? t('clone.cloning') : t('clone.workspace')}
              </button>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
