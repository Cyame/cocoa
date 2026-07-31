import {
  AlertCircle,
  ArrowUp,
  Database,
  Hash,
  LoaderCircle,
  MapPin,
  Network,
  Trash,
  Wand2,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import DistillResultModal from '@/components/DistillResultModal';
import AiGenesTab from '@/components/entity-tabs/AiGenesTab';
import BasicTab from '@/components/entity-tabs/BasicTab';
import CapabilitiesTab from '@/components/entity-tabs/CapabilitiesTab';
import DistillTab from '@/components/entity-tabs/DistillTab';
import InstancesTab from '@/components/entity-tabs/InstancesTab';
import PromoteModal from '@/components/PromoteModal';
import { ApiError } from '@/lib/api';
import {
  deleteEntity,
  type EntityDetail,
  fetchEntity,
  promoteEntity,
  transmuteEntity,
} from '@/lib/api/entities';
import { listInstancesForEntity } from '@/lib/api/learning';
import {
  deleteInstanceById,
  restartInstance,
  stopInstance,
} from '@/lib/api/instances';
import type { AvatarDisplayStatus, EntityInstanceStatus, MemoryKind, TransmuteResult } from '@/lib/types';
import { cn } from '@/lib/utils';
import { type EntityModalTabId, useEntityModalStore } from '@/stores/entityModalStore';
import { useSelectedStore } from '@/stores/selected';

const TAB_ORDER: readonly EntityModalTabId[] = [
  'basic',
  'capabilities',
  'ai_genes',
  'instances',
  'distill',
];

function resolveDisplayStatus(
  status: string,
  displayStatus: string | null | undefined,
  inConversation: boolean,
): AvatarDisplayStatus {
  if (
    displayStatus === 'busy' ||
    displayStatus === 'idle' ||
    displayStatus === 'stopped' ||
    displayStatus === 'starting' ||
    displayStatus === 'restarting' ||
    displayStatus === 'deleting' ||
    displayStatus === 'start_failed'
  ) {
    return displayStatus;
  }
  if (status === 'running') return inConversation ? 'busy' : 'idle';
  if (status === 'pending') return 'stopped';
  if (status === 'restarting') return 'restarting';
  if (status === 'deleting') return 'deleting';
  if (status === 'failed') return 'start_failed';
  if (status === 'creating' || status === 'deploying') return 'starting';
  return 'idle';
}

type EntityDetailModalProps = {
  readonly onClose: () => void;
};

export default function EntityDetailModal({ onClose }: EntityDetailModalProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const entityId = useEntityModalStore((state) => state.entityId);
  const initialTab = useEntityModalStore((state) => state.initialTab);
  const closeModal = useEntityModalStore((state) => state.close);
  const [tab, setTab] = useState<EntityModalTabId>('basic');
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [instances, setInstances] = useState<readonly EntityInstanceStatus[]>([]);
  const [instancesLoading, setInstancesLoading] = useState(false);
  const [instancesError, setInstancesError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  const [transmuteResult, setTransmuteResult] = useState<TransmuteResult | null>(null);
  const [promoteInstance, setPromoteInstance] = useState<EntityInstanceStatus | null>(null);
  const [deletingEntity, setDeletingEntity] = useState(false);
  const tabListRef = useRef<HTMLDivElement | null>(null);

  const loadEntity = useCallback(
    async (id: string) => {
      setLoadError(null);
      try {
        const next = await fetchEntity(id);
        setEntity(next);
      } catch (error) {
        if (error instanceof ApiError) {
          setLoadError(error.message);
          return;
        }
        setLoadError(t('entityModal.loadFailed'));
      }
    },
    [t],
  );

  const loadInstances = useCallback(
    async (id: string) => {
      setInstancesLoading(true);
      setInstancesError(null);
      try {
        const page = await listInstancesForEntity(id);
        const items: EntityInstanceStatus[] = page.items.map((it) => ({
          id: it.id,
          entity_id: it.entity_id,
          workspace_id: it.workspace_id,
          status: it.status,
          display_status: resolveDisplayStatus(
            it.status,
            it.display_status,
            it.in_conversation === true,
          ),
          in_conversation: it.in_conversation === true,
          continuation_count: 0,
          last_checkpoint_at: null,
          pod_name: null,
          spawn_time: it.created_at,
          last_active_at: it.updated_at,
        }));
        setInstances(items);
      } catch (error) {
        if (error instanceof ApiError) {
          setInstancesError(error.message);
          return;
        }
        setInstancesError(t('errors.network'));
      } finally {
        setInstancesLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (entityId === null) return;
    setTab(initialTab ?? 'basic');
    void loadEntity(entityId);
    void loadInstances(entityId);
  }, [entityId, initialTab, loadEntity, loadInstances]);

  useEffect(() => {
    if (entityId === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [entityId, onClose]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(id);
  }, [toast]);

  const moveTab = useCallback(
    (direction: 1 | -1) => {
      const idx = TAB_ORDER.indexOf(tab);
      const next = (idx + direction + TAB_ORDER.length) % TAB_ORDER.length;
      const target = TAB_ORDER[next];
      if (target !== undefined) setTab(target);
    },
    [tab],
  );

  const handleTabKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        moveTab(1);
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        moveTab(-1);
      } else if (event.key === 'Home') {
        event.preventDefault();
        setTab('basic');
      } else if (event.key === 'End') {
        event.preventDefault();
        setTab('distill');
      }
    },
    [moveTab],
  );

  const canEdit = true;
  const canTransmute = true;

  const handleDeleteEntity = useCallback(async () => {
    if (entityId === null || entity === null || deletingEntity) return;
    const ok = window.confirm(
      t('entityModal.footer.deleteConfirmBody', {
        name: entity.display_name ?? entity.name,
      }),
    );
    if (!ok) return;
    setDeletingEntity(true);
    try {
      await deleteEntity(entityId);
      closeModal();
      onClose();
    } catch (error) {
      let message = t('entityModal.errors.delete');
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
          message = translated.length > 0 ? translated : error.message;
        } else {
          message = error.message;
        }
      }
      setToast({ kind: 'error', message });
    } finally {
      setDeletingEntity(false);
    }
  }, [closeModal, deletingEntity, entity, entityId, onClose, t]);

  const handlePromote = useCallback(
    async (payload: import('@/lib/api/entities').PromotePayload) => {
      if (entityId === null) return;
      const result = await promoteEntity(entityId, {
        ...payload,
        from_instance_id: payload.from_instance_id ?? promoteInstance?.id ?? null,
      });
      const message =
        result.mode === 'fork'
          ? t('promoteModal.successFork')
          : t('promoteModal.successUpdate', { count: result.outdated_instances_count });
      setToast({ kind: 'success', message });
      setPromoteInstance(null);
    },
    [entityId, promoteInstance, t],
  );

  const handleTransmute = useCallback(
    async (targetSlug: string, targetName: string, kinds: readonly MemoryKind[] | null) => {
      if (entityId === null) return;
      const result = await transmuteEntity(entityId, targetSlug, targetName, kinds);
      setTransmuteResult(result);
    },
    [entityId],
  );

  const handleReap = useCallback(
    async (inst: EntityInstanceStatus) => {
      const ok = window.confirm(
        t('entityModal.instancesTab.reapConfirmBody', { id: inst.id.slice(0, 8) }),
      );
      if (!ok) return;
      try {
        const { reapInstance } = await import('@/lib/api/learning');
        await reapInstance(inst.id, null);
        setToast({ kind: 'success', message: t('entityModal.instancesTab.reapSuccess') });
        void loadInstances(inst.entity_id);
      } catch (error) {
        const message = error instanceof ApiError ? error.message : t('entityModal.errors.reap');
        setToast({ kind: 'error', message });
      }
    },
    [loadInstances, t],
  );

  const handleDelete = useCallback(
    async (inst: EntityInstanceStatus) => {
      const ok = window.confirm(
        t('entityModal.instancesTab.deleteConfirmBody', { id: inst.id.slice(0, 8) }),
      );
      if (!ok) return;
      try {
        await deleteInstanceById(inst.id);
        setInstances((prev) => prev.filter((it) => it.id !== inst.id));
        setToast({ kind: 'success', message: t('entityModal.instancesTab.deleteSuccess') });
      } catch (error) {
        const message = error instanceof ApiError ? error.message : t('entityModal.errors.reap');
        setToast({ kind: 'error', message });
      }
    },
    [t],
  );

  const handleStop = useCallback(
    async (inst: EntityInstanceStatus) => {
      try {
        await stopInstance(inst.id);
        setInstances((prev) =>
          prev.map((it) =>
            it.id === inst.id
              ? { ...it, status: 'pending', display_status: 'stopped' as const }
              : it,
          ),
        );
        setToast({ kind: 'success', message: t('entityModal.instancesTab.stopSuccess') });
        void loadInstances(inst.entity_id);
      } catch (error) {
        const message = error instanceof ApiError ? error.message : t('entityModal.errors.reap');
        setToast({ kind: 'error', message });
      }
    },
    [loadInstances, t],
  );

  const handleRestart = useCallback(
    async (inst: EntityInstanceStatus) => {
      const ok = window.confirm(
        t('entityModal.instancesTab.restartConfirmBody', { id: inst.id.slice(0, 8) }),
      );
      if (!ok) return;
      try {
        await restartInstance(inst.id, { force: true });
        setToast({ kind: 'success', message: t('entityModal.instancesTab.restartSuccess') });
        void loadInstances(inst.entity_id);
      } catch (error) {
        const message = error instanceof ApiError ? error.message : t('entityModal.errors.reap');
        setToast({ kind: 'error', message });
      }
    },
    [loadInstances, t],
  );

  const handleRemoveCapability = useCallback(
    (cap: { name: string }) => {
      setToast({ kind: 'success', message: t('entityModal.capabilitiesTab.removeSuccess') });
      void cap;
    },
    [t],
  );

  const handleRemoveGene = useCallback(() => {
    setToast({ kind: 'success', message: 'gene removed (local only)' });
  }, []);

  const handleUpdated = useCallback((next: EntityDetail) => {
    setEntity(next);
  }, []);

  const handleFindInWorkspace = useCallback(() => {
    const first = instances[0];
    if (first === undefined || !first.workspace_id) {
      setToast({ kind: 'error', message: t('entityModal.footer.findInTopologyEmpty') });
      return;
    }
    useSelectedStore.getState().setWorkspaceId(first.workspace_id);
    useSelectedStore.getState().setInstanceId(first.id);
    navigate(`/workspaces/${encodeURIComponent(first.workspace_id)}`);
    onClose();
  }, [instances, navigate, onClose, t]);

  const handleGoWorkspace = useCallback(
    (inst: EntityInstanceStatus) => {
      if (!inst.workspace_id) {
        setToast({
          kind: 'error',
          message: t('entityModal.instancesTab.goToWorkspaceMissing'),
        });
        return;
      }
      // Navigate first, then close — closing unmounts this modal via zustand.
      useSelectedStore.getState().setWorkspaceId(inst.workspace_id);
      useSelectedStore.getState().setInstanceId(inst.id);
      navigate(`/workspaces/${encodeURIComponent(inst.workspace_id)}`);
      onClose();
    },
    [navigate, onClose, t],
  );

  const handleGoToGenes = useCallback(() => {
    setTab('ai_genes');
  }, []);

  const handleAddGene = useCallback(() => {
    setToast({ kind: 'success', message: t('entityModal.aiGenesTab.addExtraHint') });
  }, [t]);

  const headerTitle = useMemo(() => {
    if (entity === null) return t('entityModal.title');
    return entity.display_name ?? entity.name;
  }, [entity, t]);

  if (entityId === null) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="entity-modal-title"
      data-testid="entity-detail-modal"
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 p-0 md:items-center md:p-4"
    >
      <div
        className={cn(
          'flex w-full flex-col overflow-hidden bg-white shadow-2xl',
          'h-[100dvh] rounded-t-2xl md:h-auto md:max-h-[80vh] md:w-[920px] md:rounded-2xl',
        )}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">
              {t('entityModal.title')}
            </p>
            <h2
              id="entity-modal-title"
              data-testid="entity-modal-title"
              className="mt-1 truncate text-xl font-semibold tracking-tight text-slate-950"
            >
              {headerTitle}
            </h2>
            {entity !== null ? (
              <p
                className="mt-0.5 flex items-center gap-1 font-mono text-xs text-slate-500"
                data-testid="entity-modal-slug"
              >
                <Hash className="size-3" aria-hidden="true" />
                {entity.slug}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('entityModal.close')}
            data-testid="entity-modal-close"
            className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        <div
          ref={tabListRef}
          role="tablist"
          aria-label={t('entityModal.tablist')}
          className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-slate-50 px-3 py-2"
          data-testid="entity-modal-tabs"
        >
          {TAB_ORDER.map((id) => {
            const active = tab === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                tabIndex={active ? 0 : -1}
                onClick={() => setTab(id)}
                onKeyDown={handleTabKeyDown}
                data-testid={`entity-tab-${id}`}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                  active
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:bg-white hover:text-slate-900',
                )}
              >
                {t(`entityModal.tabs.${id}`)}
              </button>
            );
          })}
        </div>

        {toast ? (
          <div
            role={toast.kind === 'error' ? 'alert' : 'status'}
            data-testid="entity-modal-toast"
            className={cn(
              'mx-5 mt-3 flex items-center gap-2 rounded-lg border px-4 py-2 text-sm',
              toast.kind === 'error'
                ? 'border-red-200 bg-red-50 text-red-800'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800',
            )}
          >
            {toast.kind === 'error' ? (
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
            ) : null}
            <p>{toast.message}</p>
          </div>
        ) : null}

        <div
          role="tabpanel"
          aria-labelledby={`entity-tab-${tab}`}
          className="min-h-0 flex-1 overflow-y-auto px-5 py-5"
          data-testid="entity-modal-panel"
        >
          {loadError !== null ? (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <p>{loadError}</p>
            </div>
          ) : entity === null ? (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 p-8 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('entityModal.loading')}
            </div>
          ) : tab === 'basic' ? (
            <BasicTab
              entity={entity}
              canEdit={canEdit}
              onUpdated={handleUpdated}
              onFindInWorkspace={handleFindInWorkspace}
            />
          ) : tab === 'capabilities' ? (
            <CapabilitiesTab
              entity={entity}
              onGoToGenes={handleGoToGenes}
              onRemove={handleRemoveCapability}
            />
          ) : tab === 'ai_genes' ? (
            <AiGenesTab entity={entity} onAdd={handleAddGene} onRemove={handleRemoveGene} />
          ) : tab === 'instances' ? (
            <InstancesTab
              instances={instances}
              isLoading={instancesLoading}
              errorMessage={instancesError}
              onPromote={(inst) => setPromoteInstance(inst)}
              onReap={handleReap}
              onDelete={handleDelete}
              onStop={handleStop}
              onRestart={handleRestart}
              onGoWorkspace={handleGoWorkspace}
            />
          ) : (
            <DistillTab entity={entity} canTransmute={canTransmute} onTransmute={handleTransmute} />
          )}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleFindInWorkspace}
              data-testid="entity-footer-memory"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <Database className="size-3.5" aria-hidden="true" />
              {t('entityModal.footer.viewWorkspaceMemory')}
            </button>
            <button
              type="button"
              onClick={handleFindInWorkspace}
              data-testid="entity-footer-topology"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <MapPin className="size-3.5" aria-hidden="true" />
              {t('entityModal.footer.findInTopology')}
            </button>
          </div>
          <div className="flex items-center gap-2">
            {canEdit && entity !== null ? (
              <button
                type="button"
                disabled={deletingEntity}
                onClick={() => {
                  void handleDeleteEntity();
                }}
                data-testid="entity-footer-delete"
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-60"
              >
                {deletingEntity ? (
                  <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Trash className="size-3.5" aria-hidden="true" />
                )}
                {t('entityModal.footer.deleteEntity')}
              </button>
            ) : null}
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Network className="size-3.5" aria-hidden="true" />
              <ArrowUp className="size-3.5" aria-hidden="true" />
              <Wand2 className="size-3.5" aria-hidden="true" />
            </div>
          </div>
        </footer>
      </div>

      <DistillResultModal result={transmuteResult} onClose={() => setTransmuteResult(null)} />

      {promoteInstance !== null && entity !== null ? (
        <PromoteModal
          entity={entity}
          instanceCount={instances.length}
          fromInstanceId={promoteInstance.id}
          onClose={() => setPromoteInstance(null)}
          onSubmit={handlePromote}
        />
      ) : null}
    </div>
  );
}

