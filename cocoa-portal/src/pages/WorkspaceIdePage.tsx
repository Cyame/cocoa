import {
  AlertCircle,
  Archive,
  Brain,
  CalendarDays,
  Cpu,
  FilePlus,
  FileText,
  Folder,
  FolderPlus,
  LoaderCircle,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash,
  UserRound,
  Users,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import IdeShell from '@/components/IdeShell';
import InstancesPanel from '@/components/InstancesPanel';
import IntroduceInstanceModal from '@/components/IntroduceInstanceModal';
import MeetingPanel from '@/components/MeetingPanel';
import { ModelInputCombobox } from '@/components/ModelInputCombobox';
import SchedulesPanel from '@/components/SchedulesPanel';
import { ApiError, api } from '@/lib/api';
import {
  archiveFornixFile,
  createFornixFile,
  deleteFornixFile,
  type FornixFile,
  fetchFornixFile,
  listFornixFiles,
  listVaultEntries,
  patchFornixFile,
  restoreVaultEntry,
  type VaultEntry,
} from '@/lib/api/fornix';
import { deleteInstanceById, deleteMembership } from '@/lib/api/instances';
import { fetchLiveStatus } from '@/lib/api/liveStatus';
import {
  type CatalogModel,
  type CerebellumAgent,
  type CerebellumDefaults,
  fetchCerebellumDefaults,
  fetchModelCatalog,
  fetchWorkspaceCerebellum,
  listOrganizationProviders,
  type OrganizationProvider,
  patchWorkspaceCerebellum,
} from '@/lib/api/providers';
import { fetchWorkspace } from '@/lib/api/workspaces';
import type {
  Entity,
  Instance,
  LiveStatusItem,
  LoopStatus,
  Membership,
  Workspace,
} from '@/lib/types';
import TopologyPage from '@/pages/TopologyPage';
import { useSelectedStore } from '@/stores/selected';
import { useSessionStore } from '@/stores/session';

type CanvasTab = 'topology' | 'memberships' | 'instances' | 'meetings' | 'brain';
type BrainSubTab = 'fornix' | 'vault' | 'frontal' | 'brainstem' | 'cerebellum';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

type CentralHub = {
  readonly id: string;
  readonly workspace_id: string;
  readonly content: string | null;
  readonly manual_notes: string | null;
};

const LIVE_STATUS_INTERVAL_MS = 5000;

const GLOW_TO_STATUS: Readonly<Record<string, LoopStatus | 'unknown'>> = {
  '#10b981': 'running',
  '#eab308': 'idle',
  '#94a3b8': 'paused',
  '#ef4444': 'interrupted',
  '#3b82f6': 'completed',
  '#dc2626': 'failed',
};

function deriveHealth(liveStatus: readonly LiveStatusItem[]): string {
  for (const item of liveStatus) {
    if (item.node_type !== 'instance') continue;
    const status = GLOW_TO_STATUS[item.glow.color.toLowerCase()] ?? 'unknown';
    if (status === 'failed') return 'failed';
    if (status === 'interrupted' || status === 'paused') return 'warning';
  }
  return 'healthy';
}

export default function WorkspaceIdePage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const setWorkspaceId = useSelectedStore((state) => state.setWorkspaceId);
  const interactionMode = useSelectedStore((state) => state.interactionMode);
  const currentUserId = useSessionStore((state) => state.user?.user_id ?? null);

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [activeTab, setActiveTab] = useState<CanvasTab>('topology');
  const [brainSubTab, setBrainSubTab] = useState<BrainSubTab>('fornix');
  const [memberships, setMemberships] = useState<readonly Membership[]>([]);
  const [instances, setInstances] = useState<readonly Instance[]>([]);
  const [entities, setEntities] = useState<readonly Entity[]>([]);
  const [centralHub, setCentralHub] = useState<CentralHub | null>(null);
  const [cerebellum, setCerebellum] = useState<CerebellumAgent | null>(null);
  const [worldCerebellumDefaults, setWorldCerebellumDefaults] = useState<CerebellumDefaults | null>(
    null,
  );
  const [liveStatus, setLiveStatus] = useState<readonly LiveStatusItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [introduceOpen, setIntroduceOpen] = useState(false);
  const [topologyRefreshKey, setTopologyRefreshKey] = useState(0);
  const [brainRefreshKey, setBrainRefreshKey] = useState(0);

  const bumpBrainRefresh = useCallback(() => setBrainRefreshKey((key) => key + 1), []);

  useEffect(() => {
    if (id === undefined) return;
    setWorkspaceId(id);
    return () => setWorkspaceId(null);
  }, [id, setWorkspaceId]);

  const loadData = useCallback(async () => {
    if (id === undefined) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [ws, membershipPage, instancePage, entityPage, hub, cerebellumAgent, defaults] =
        await Promise.all([
          fetchWorkspace(id),
          api<OffsetPage<Membership>>(
            `/messaging/memberships?workspace_id=${encodeURIComponent(id)}&kind=user`,
          ),
          api<OffsetPage<Instance>>(`/instances?workspace_id=${encodeURIComponent(id)}`),
          api<OffsetPage<Entity>>('/entities?limit=200&is_cerebellum=false'),
          api<CentralHub>(`/central-hubs/${encodeURIComponent(id)}`).catch(() => null),
          fetchWorkspaceCerebellum(id).catch(() => null),
          fetchCerebellumDefaults().catch(() => null),
        ]);
      setWorkspace(ws);
      setMemberships(membershipPage.items);
      setInstances(instancePage.items);
      setEntities(entityPage.items);
      if (hub !== null) setCentralHub(hub);
      if (cerebellumAgent !== null) setCerebellum(cerebellumAgent);
      if (defaults !== null) setWorldCerebellumDefaults(defaults);
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage(t('errors.network'));
      }
    } finally {
      setIsLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (id === undefined) return;
    // Topology tab already polls live-status; avoid doubling and hitting 429.
    if (activeTab === 'topology') return;
    const workspaceId = id;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        const items = await fetchLiveStatus(workspaceId);
        if (!cancelled) setLiveStatus(items);
      } catch {
        // best-effort
      } finally {
        if (!cancelled) timerId = setTimeout(poll, LIVE_STATUS_INTERVAL_MS);
      }
    }

    timerId = setTimeout(poll, 0);
    return () => {
      cancelled = true;
      if (timerId !== null) clearTimeout(timerId);
    };
  }, [id, activeTab]);

  const resolveActionError = useCallback(
    (error: unknown, fallbackKey: string) => {
      if (error instanceof ApiError) {
        const payload = error.payload;
        if (
          typeof payload === 'object' &&
          payload !== null &&
          'message_key' in payload &&
          typeof (payload as { message_key: unknown }).message_key === 'string'
        ) {
          const key = (payload as { message_key: string }).message_key;
          const translated = t(key, { defaultValue: '' });
          if (translated.length > 0) return translated;
        }
        return error.message;
      }
      return t(fallbackKey);
    },
    [t],
  );

  const handleRemoveMembership = useCallback(
    async (membershipId: string, label: string) => {
      const ok = window.confirm(t('workspace.removeAwakenedConfirm', { name: label }));
      if (!ok) return;
      try {
        await deleteMembership(membershipId);
        setTopologyRefreshKey((k) => k + 1);
        await loadData();
      } catch (error) {
        setErrorMessage(resolveActionError(error, 'workspace.removeFailed'));
      }
    },
    [loadData, resolveActionError, t],
  );

  const handleRemoveInstance = useCallback(
    async (instanceId: string, label: string) => {
      const ok = window.confirm(t('workspace.removeLostOneConfirm', { name: label }));
      if (!ok) return;
      try {
        await deleteInstanceById(instanceId);
        setTopologyRefreshKey((k) => k + 1);
        await loadData();
      } catch (error) {
        setErrorMessage(resolveActionError(error, 'workspace.removeFailed'));
      }
    },
    [loadData, resolveActionError, t],
  );

  const healthKey = useMemo(() => deriveHealth(liveStatus), [liveStatus]);
  const healthLabel = t(
    `workspaceHeader.health.${healthKey === 'warning' ? 'warning' : healthKey === 'failed' ? 'failed' : 'healthy'}`,
  );
  const modeLabel = t(`topology.mode.${interactionMode}`);

  const TABS: readonly { id: CanvasTab; label: string; Icon: typeof Users }[] = [
    { id: 'topology', label: t('workspace.tabs.topology'), Icon: Users },
    { id: 'memberships', label: t('workspace.tabs.memberships'), Icon: Users },
    { id: 'instances', label: t('workspace.tabs.instances'), Icon: Cpu },
    { id: 'meetings', label: t('workspace.tabs.meetings'), Icon: CalendarDays },
    { id: 'brain', label: t('workspace.tabs.brain'), Icon: Brain },
  ];

  if (id === undefined) {
    return <p className="p-6 text-sm text-red-700">{t('workspace.idMissing')}</p>;
  }

  return (
    <IdeShell
      workspaceId={id}
      workspaceName={workspace?.name ?? id}
      healthLabel={healthLabel}
      modeLabel={modeLabel}
    >
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 pt-2">
          {TABS.map(({ id: tabId, label, Icon }) => (
            <button
              key={tabId}
              type="button"
              role="tab"
              aria-selected={activeTab === tabId}
              onClick={() => setActiveTab(tabId)}
              className={`inline-flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium ${
                activeTab === tabId
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-transparent text-slate-500 hover:bg-slate-50'
              }`}
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {errorMessage !== null ? (
            <div
              role="alert"
              className="m-4 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <p>{errorMessage}</p>
            </div>
          ) : null}

          {isLoading && activeTab !== 'topology' ? (
            <div className="flex h-full items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
              {t('common.loading')}
            </div>
          ) : null}

          {activeTab === 'topology' ? (
            <div className="flex h-full flex-col">
              <div className="flex shrink-0 justify-end border-b border-slate-200 bg-white px-3 py-2">
                <button
                  type="button"
                  onClick={() => setIntroduceOpen(true)}
                  data-testid="workspace-introduce-topology"
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
                >
                  <Plus className="size-3.5" aria-hidden="true" />
                  {t('workspace.introduceInstance')}
                </button>
              </div>
              <div className="min-h-0 flex-1">
                <TopologyPage
                  embedded
                  workspaceId={id}
                  refreshKey={topologyRefreshKey}
                  onOpenBrain={() => {
                    setActiveTab('brain');
                    setBrainSubTab('fornix');
                  }}
                />
              </div>
            </div>
          ) : null}

          {!isLoading && activeTab === 'memberships' ? (
            <PanelList
              emptyTitle={t('workspace.emptyMembershipsTitle')}
              emptyDetail={t('workspace.emptyMembershipsDetail')}
              items={memberships.map((m) => {
                const isMe = currentUserId !== null && m.user_id === currentUserId;
                const name = m.nickname?.trim() || m.username?.trim() || t('topology.userLabel');
                const title = isMe ? t('topology.meLabel', { name }) : name;
                return {
                  id: m.id,
                  title,
                  subtitle: isMe ? t('workspace.meBadge') : '',
                  removeLabel: t('workspace.removeAwakened'),
                  onRemove: () => {
                    void handleRemoveMembership(m.id, name);
                  },
                };
              })}
              actionLabel={t('workspace.introduceInstance')}
              onAction={() => setIntroduceOpen(true)}
            />
          ) : null}

          {!isLoading && activeTab === 'instances' ? (
            <InstancesPanel
              instances={instances}
              entities={entities}
              emptyTitle={t('workspace.emptyInstancesTitle')}
              emptyDetail={t('workspace.emptyInstancesDetail')}
              actionLabel={t('workspace.introduceInstance')}
              onAction={() => setIntroduceOpen(true)}
              removeLabel={t('workspace.removeLostOne')}
              onRemove={(instanceId, title) => {
                void handleRemoveInstance(instanceId, title);
              }}
            />
          ) : null}

          {!isLoading && activeTab === 'meetings' ? <MeetingPanel workspaceId={id} /> : null}

          {!isLoading && activeTab === 'brain' ? (
            <div className="flex h-full flex-col">
              <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-slate-50 px-4 py-2">
                {(['fornix', 'vault', 'frontal', 'brainstem', 'cerebellum'] as const).map(
                  (subTab) => (
                    <button
                      key={subTab}
                      type="button"
                      role="tab"
                      aria-selected={brainSubTab === subTab}
                      onClick={() => setBrainSubTab(subTab)}
                      className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                        brainSubTab === subTab
                          ? 'bg-white text-slate-900 shadow-sm'
                          : 'text-slate-600 hover:bg-white'
                      }`}
                    >
                      {t(`workspace.brain.${subTab}`)}
                    </button>
                  ),
                )}
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-6">
                {brainSubTab === 'cerebellum' ? (
                  <CerebellumPanel
                    workspaceId={id}
                    cerebellum={cerebellum}
                    worldDefaults={worldCerebellumDefaults}
                    onUpdated={(next) => setCerebellum(next)}
                  />
                ) : brainSubTab === 'fornix' ? (
                  <FornixPanel
                    workspaceId={id}
                    hub={centralHub}
                    refreshKey={brainRefreshKey}
                    onMutated={bumpBrainRefresh}
                  />
                ) : brainSubTab === 'vault' ? (
                  <VaultPanel
                    workspaceId={id}
                    refreshKey={brainRefreshKey}
                    onMutated={bumpBrainRefresh}
                  />
                ) : brainSubTab === 'frontal' ? (
                  <BrainRegionPanel
                    workspaceId={id}
                    title={t('workspace.brain.frontal')}
                    empty={t('workspace.brain.frontalEmpty')}
                  />
                ) : (
                  <SchedulesPanel workspaceId={id} />
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {introduceOpen ? (
        <IntroduceInstanceModal
          workspaceId={id}
          onClose={() => setIntroduceOpen(false)}
          onIntroduced={() => {
            void loadData();
            setTopologyRefreshKey((k) => k + 1);
          }}
        />
      ) : null}
    </IdeShell>
  );
}

function BrainRegionPanel({
  workspaceId,
  title,
  empty,
}: {
  readonly workspaceId: string;
  readonly title: string;
  readonly empty: string;
}) {
  const { t } = useTranslation();
  const [items, setItems] = useState<readonly { id: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const path = `/central-hubs/${encodeURIComponent(workspaceId)}/frontal-lobe/kanbans`;
    void api<unknown>(path)
      .then((res) => {
        if (cancelled) return;
        const raw: readonly Record<string, unknown>[] = Array.isArray(res)
          ? (res as readonly Record<string, unknown>[])
          : Array.isArray((res as { items?: unknown }).items)
            ? (res as { items: readonly Record<string, unknown>[] }).items
            : [];
        setItems(
          raw.map((row: Record<string, unknown>, index: number) => ({
            id: String(row.id ?? index),
            label: String(
              row.name ?? row.title ?? row.cron_expr ?? row.path ?? row.id ?? `#${index + 1}`,
            ),
          })),
        );
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return (
    <div className="space-y-4">
      <article className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {loading ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {t('common.loading')}
          </p>
        ) : items.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">{empty}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700"
              >
                {item.label}
              </li>
            ))}
          </ul>
        )}
      </article>
    </div>
  );
}

function joinHubPath(parent: string, name: string): string {
  return parent.length > 0 ? `${parent}/${name}` : name;
}

function FornixPanel({
  workspaceId,
  hub,
  refreshKey,
  onMutated,
}: {
  readonly workspaceId: string;
  readonly hub: CentralHub | null;
  readonly refreshKey: number;
  readonly onMutated: () => void;
}) {
  const { t } = useTranslation();
  const [items, setItems] = useState<readonly FornixFile[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parentPath, setParentPath] = useState('');
  const [viewing, setViewing] = useState<FornixFile | null>(null);
  const [viewContent, setViewContent] = useState<string | null>(null);
  const [viewingLoading, setViewingLoading] = useState(false);
  const [creating, setCreating] = useState<'file' | 'directory' | null>(null);
  const [createName, setCreateName] = useState('');
  const [createContent, setCreateContent] = useState('');
  const [editing, setEditing] = useState<FornixFile | null>(null);
  const [editName, setEditName] = useState('');
  const [editParentPath, setEditParentPath] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (path: string) => {
      setLoading(true);
      setError(null);
      try {
        const page = await listFornixFiles(workspaceId, {
          parent_path: path.length > 0 ? path : undefined,
        });
        setItems(page.items);
        setTotal(page.total);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t('errors.network'));
        setItems([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [t, workspaceId],
  );

  useEffect(() => {
    void load(parentPath);
  }, [load, parentPath, refreshKey]);

  const segments = useMemo(
    () => parentPath.split('/').filter((segment) => segment.length > 0),
    [parentPath],
  );

  function handleOpenDirectory(dir: FornixFile) {
    setViewing(null);
    setParentPath(joinHubPath(parentPath, dir.name));
  }

  async function handleView(file: FornixFile) {
    setViewing(file);
    setViewContent(null);
    setViewingLoading(true);
    setError(null);
    try {
      const detail = await fetchFornixFile(workspaceId, file.id);
      setViewContent(detail.content);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setViewingLoading(false);
    }
  }

  async function handleCreate() {
    if (creating === null || createName.trim().length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await createFornixFile(workspaceId, {
        workspace_id: workspaceId,
        name: createName.trim(),
        parent_path: parentPath.length > 0 ? parentPath : null,
        content: creating === 'file' ? createContent : null,
        is_directory: creating === 'directory',
      });
      setCreating(null);
      setCreateName('');
      setCreateContent('');
      onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(file: FornixFile) {
    const ok = window.confirm(t('workspace.fornix.deleteConfirm', { name: file.name }));
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await deleteFornixFile(workspaceId, file.id);
      if (viewing?.id === file.id) setViewing(null);
      onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  }

  async function handleArchive(file: FornixFile) {
    const ok = window.confirm(t('workspace.fornix.archiveConfirm', { name: file.name }));
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await archiveFornixFile(workspaceId, file.id);
      if (viewing?.id === file.id) setViewing(null);
      onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  }

  async function handleRenameSave() {
    if (editing === null) return;
    setBusy(true);
    setError(null);
    try {
      await patchFornixFile(workspaceId, editing.id, {
        name: editName.trim().length > 0 ? editName.trim() : undefined,
        parent_path: editParentPath.trim().length > 0 ? editParentPath.trim() : null,
      });
      setEditing(null);
      onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {hub !== null ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold">{t('workspace.sharedContext')}</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate-600">
              {hub.content ?? t('workspace.noSharedContext')}
            </p>
          </article>
          <article className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold">{t('workspace.manualNotes')}</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate-600">
              {hub.manual_notes ?? t('workspace.noManualNotes')}
            </p>
          </article>
        </div>
      ) : null}

      <article className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">{t('workspace.fornix.title')}</h2>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setCreating('file');
              }}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
            >
              <FilePlus className="size-3.5" aria-hidden="true" />
              {t('workspace.fornix.newFile')}
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setCreating('directory');
              }}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              <FolderPlus className="size-3.5" aria-hidden="true" />
              {t('workspace.fornix.newFolder')}
            </button>
          </div>
        </div>

        <nav
          aria-label={t('workspace.fornix.title')}
          className="mt-3 flex flex-wrap items-center gap-1 text-xs text-slate-500"
        >
          <button
            type="button"
            onClick={() => setParentPath('')}
            className="rounded px-1.5 py-0.5 hover:bg-slate-100 hover:text-slate-700"
          >
            {t('workspace.fornix.root')}
          </button>
          {segments.map((segment, index) => (
            <span key={`${segment}-${index}`} className="flex items-center gap-1">
              <span aria-hidden="true">/</span>
              <button
                type="button"
                onClick={() => setParentPath(segments.slice(0, index + 1).join('/'))}
                className="rounded px-1.5 py-0.5 hover:bg-slate-100 hover:text-slate-700"
              >
                {segment}
              </button>
            </span>
          ))}
        </nav>

        {error !== null ? (
          <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {t('common.loading')}
          </p>
        ) : items.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">{t('workspace.fornix.empty')}</p>
        ) : (
          <>
            <ul className="mt-3 space-y-2">
              {items.map((file) => (
                <li
                  key={file.id}
                  className="flex items-center gap-3 rounded-md border border-slate-100 bg-slate-50 px-3 py-2"
                >
                  {file.is_directory ? (
                    <Folder className="size-4 shrink-0 text-slate-500" aria-hidden="true" />
                  ) : (
                    <FileText className="size-4 shrink-0 text-slate-500" aria-hidden="true" />
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      file.is_directory ? handleOpenDirectory(file) : void handleView(file)
                    }
                    title={
                      file.is_directory
                        ? t('workspace.fornix.openFolder')
                        : t('workspace.fornix.viewFile')
                    }
                    className="min-w-0 flex-1 truncate text-left font-mono text-xs text-slate-700 hover:text-blue-700"
                  >
                    {file.name}
                  </button>
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setCreating(null);
                        setEditing(file);
                        setEditName(file.name);
                        setEditParentPath(file.parent_path ?? '');
                      }}
                      disabled={busy}
                      aria-label={t('workspace.fornix.rename')}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-60"
                    >
                      <Pencil className="size-3.5" aria-hidden="true" />
                    </button>
                    {!file.is_directory ? (
                      <button
                        type="button"
                        onClick={() => void handleArchive(file)}
                        disabled={busy}
                        aria-label={t('workspace.fornix.archive')}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-60"
                      >
                        <Archive className="size-3.5" aria-hidden="true" />
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => void handleDelete(file)}
                      disabled={busy}
                      aria-label={t('workspace.fornix.delete')}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                    >
                      <Trash className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-400">{t('workspace.fornix.count', { total })}</p>
          </>
        )}
      </article>

      {viewing !== null ? (
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="min-w-0 truncate font-mono text-xs font-semibold text-slate-900">
              {viewing.name}
            </h3>
            <button
              type="button"
              onClick={() => setViewing(null)}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
            >
              {t('common.close')}
            </button>
          </div>
          {viewingLoading ? (
            <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('common.loading')}
            </p>
          ) : (
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
              {viewContent ?? t('workspace.fornix.emptyContent')}
            </pre>
          )}
        </article>
      ) : null}

      {creating !== null ? (
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold text-slate-900">
            {creating === 'directory'
              ? t('workspace.fornix.createFolderTitle')
              : t('workspace.fornix.createFileTitle')}
          </h3>
          <form
            className="mt-3 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void handleCreate();
            }}
          >
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('workspace.fornix.name')}
              <input
                value={createName}
                onChange={(event) => setCreateName(event.target.value)}
                autoFocus
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            {creating === 'file' ? (
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
                {t('workspace.fornix.content')}
                <textarea
                  value={createContent}
                  onChange={(event) => setCreateContent(event.target.value)}
                  rows={6}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs"
                />
              </label>
            ) : null}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={busy || createName.trim().length === 0}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
              >
                {creating === 'directory'
                  ? t('workspace.fornix.createFolder')
                  : t('workspace.fornix.createFile')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setCreating(null);
                  setCreateName('');
                  setCreateContent('');
                }}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                {t('common.cancel')}
              </button>
            </div>
          </form>
        </article>
      ) : null}

      {editing !== null ? (
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold text-slate-900">
            {t('workspace.fornix.renameTitle')}
          </h3>
          <form
            className="mt-3 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void handleRenameSave();
            }}
          >
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('workspace.fornix.name')}
              <input
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('workspace.fornix.parentPath')}
              <input
                value={editParentPath}
                onChange={(event) => setEditParentPath(event.target.value)}
                placeholder={t('workspace.fornix.parentPathPlaceholder')}
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
              >
                {t('workspace.fornix.rename')}
              </button>
              <button
                type="button"
                onClick={() => setEditing(null)}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                {t('common.cancel')}
              </button>
            </div>
          </form>
        </article>
      ) : null}
    </div>
  );
}

function VaultPanel({
  workspaceId,
  refreshKey,
  onMutated,
}: {
  readonly workspaceId: string;
  readonly refreshKey: number;
  readonly onMutated: () => void;
}) {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<readonly VaultEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [searchDraft, setSearchDraft] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(
    async (archivedKey: string) => {
      setLoading(true);
      setError(null);
      try {
        const page = await listVaultEntries(workspaceId, {
          archived_key: archivedKey.trim().length > 0 ? archivedKey.trim() : undefined,
        });
        setEntries(page.items);
        setTotal(page.total);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t('errors.network'));
        setEntries([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [t, workspaceId],
  );

  useEffect(() => {
    void load(search);
  }, [load, refreshKey, search]);

  async function handleRestore(entry: VaultEntry) {
    const ok = window.confirm(
      t('workspace.vault.restoreConfirm', { key: entry.archived_key ?? entry.id }),
    );
    if (!ok) return;
    setBusyId(entry.id);
    setError(null);
    try {
      await restoreVaultEntry(workspaceId, entry.id);
      onMutated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <article className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">{t('workspace.vault.title')}</h2>
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchDraft);
            }}
          >
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder={t('workspace.vault.searchPlaceholder')}
              className="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
            >
              <Search className="size-3.5" aria-hidden="true" />
              {t('workspace.vault.search')}
            </button>
            {search.length > 0 ? (
              <button
                type="button"
                onClick={() => {
                  setSearch('');
                  setSearchDraft('');
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                {t('workspace.vault.clear')}
              </button>
            ) : null}
          </form>
        </div>

        {error !== null ? (
          <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {t('common.loading')}
          </p>
        ) : entries.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">{t('workspace.vault.empty')}</p>
        ) : (
          <>
            <ul className="mt-3 space-y-2">
              {entries.map((entry) => (
                <li
                  key={entry.id}
                  className="flex items-center gap-3 rounded-md border border-slate-100 bg-slate-50 px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-slate-700">
                      {entry.archived_key ?? entry.id}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {t('workspace.vault.archivedAt')}:{' '}
                      {entry.archived_at !== null
                        ? new Date(entry.archived_at).toLocaleString()
                        : '-'}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRestore(entry)}
                    disabled={busyId !== null}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60"
                  >
                    <RotateCcw className="size-3.5" aria-hidden="true" />
                    {t('workspace.vault.restore')}
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-400">{t('workspace.vault.count', { total })}</p>
          </>
        )}
      </article>
    </div>
  );
}

function CerebellumPanel({
  workspaceId,
  cerebellum,
  worldDefaults,
  onUpdated,
}: {
  readonly workspaceId: string;
  readonly cerebellum: CerebellumAgent | null;
  readonly worldDefaults: CerebellumDefaults | null;
  readonly onUpdated: (next: CerebellumAgent) => void;
}) {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<readonly OrganizationProvider[]>([]);
  const [models, setModels] = useState<readonly CatalogModel[]>([]);
  const [providerId, setProviderId] = useState(cerebellum?.provider_id ?? '');
  const [model, setModel] = useState(cerebellum?.model ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listOrganizationProviders(true)
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

  useEffect(() => {
    setProviderId(cerebellum?.provider_id ?? '');
    setModel(cerebellum?.model ?? '');
  }, [cerebellum]);

  useEffect(() => {
    if (providerId.length === 0) {
      setModels([]);
      return;
    }
    fetchModelCatalog(providerId)
      .then((page) => setModels(page.items))
      .catch(() => setModels([]));
  }, [providerId]);

  const worldHint =
    worldDefaults?.provider_id && worldDefaults.model
      ? t('workspace.brain.worldDefaultHint', {
          provider:
            providers.find((p) => p.id === worldDefaults.provider_id)?.name ??
            worldDefaults.provider_id,
          model: worldDefaults.model,
        })
      : t('workspace.brain.noWorldDefault');

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const next = await patchWorkspaceCerebellum(workspaceId, {
        provider_id: providerId || null,
        model: model || null,
      });
      onUpdated(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="max-w-xl rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-900">
        {t('workspace.brain.cerebellumTitle')}
      </h2>
      <p className="mt-1 text-xs text-slate-500">{t('workspace.brain.cerebellumSubtitle')}</p>
      <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">{worldHint}</p>

      <div className="mt-4 space-y-3">
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('organization.fields.provider')}
          <select
            value={providerId}
            onChange={(e) => {
              setProviderId(e.target.value);
              setModel('');
            }}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">{t('workspace.brain.inheritWorld')}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('organization.fields.model')}
          <ModelInputCombobox
            aria-label={t('organization.fields.model')}
            value={model}
            onChange={setModel}
            options={models}
            disabled={providerId.length === 0}
            emptyOptionLabel={
              providerId.length === 0 ? t('workspace.brain.inheritWorld') : undefined
            }
            placeholder={t('organization.fields.modelPlaceholder')}
          />
        </div>
        {error !== null ? (
          <p role="alert" className="text-xs text-red-700">
            {error}
          </p>
        ) : null}
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
        >
          {saving ? <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" /> : null}
          {t('workspace.brain.saveCerebellum')}
        </button>
      </div>
    </article>
  );
}

function PanelList({
  items,
  emptyTitle,
  emptyDetail,
  actionLabel,
  onAction,
}: {
  readonly items: readonly {
    id: string;
    title: string;
    subtitle: string;
    removeLabel?: string;
    onRemove?: () => void;
  }[];
  readonly emptyTitle: string;
  readonly emptyDetail: string;
  readonly actionLabel?: string;
  readonly onAction?: () => void;
}) {
  if (items.length === 0) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <div>
          <UserRound className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-4 text-sm font-semibold text-slate-900">{emptyTitle}</h2>
          <p className="mt-2 text-sm text-slate-500">{emptyDetail}</p>
          {actionLabel && onAction ? (
            <button
              type="button"
              onClick={onAction}
              data-testid="workspace-introduce-cta"
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              <Plus className="size-4" aria-hidden="true" />
              {actionLabel}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {actionLabel && onAction ? (
        <div className="flex shrink-0 justify-end border-b border-slate-200 bg-white px-4 py-2">
          <button
            type="button"
            onClick={onAction}
            data-testid="workspace-introduce-cta"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
          >
            <Plus className="size-3.5" aria-hidden="true" />
            {actionLabel}
          </button>
        </div>
      ) : null}
      <ul className="space-y-3 overflow-y-auto p-6">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-4"
          >
            <span className="grid size-9 place-items-center rounded-full bg-slate-100 text-slate-600">
              <UserRound className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
              <p className="mt-1 text-xs capitalize text-slate-500">{item.subtitle}</p>
            </div>
            {item.onRemove !== undefined && item.removeLabel !== undefined ? (
              <button
                type="button"
                onClick={item.onRemove}
                data-testid={`workspace-remove-${item.id}`}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                <Trash className="size-3.5" aria-hidden="true" />
                {item.removeLabel}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
