import { AlertCircle, Building2, Copy, FlaskConical, LoaderCircle, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router';
import CloneDialog from '@/components/CloneDialog';
import { ApiError, api } from '@/lib/api';
import { fetchMe } from '@/lib/api/auth';
import { type ClonePayload, cloneEntity } from '@/lib/api/clone';
import { resolveError } from '@/lib/apiError';
import type { Entity, OrgIdentity } from '@/lib/types';
import { useEntityModalStore } from '@/stores/entityModalStore';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';
import { useSessionStore } from '@/stores/session';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export default function NamespaceEntitiesPage() {
  const { t } = useTranslation();
  const { nsId } = useParams<{ nsId: string }>();
  const user = useSessionStore((state) => state.user);
  const isSuperAdmin = user?.is_super_admin ?? false;
  const [orgIdentity, setOrgIdentity] = useState<OrgIdentity | null>(null);
  const canCloneEntity = isSuperAdmin || (orgIdentity?.atoms.includes('can_clone_entity') ?? false);

  const [entities, setEntities] = useState<readonly Entity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [cloningId, setCloningId] = useState<string | null>(null);
  const [cloneTarget, setCloneTarget] = useState<Entity | null>(null);

  const openOnboarding = useOnboardingModalStore((state) => state.open);
  const openEntityModal = useEntityModalStore((state) => state.open);

  useEffect(() => {
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
  }, []);

  const refresh = useCallback(async () => {
    if (nsId === undefined) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const page = await api<OffsetPage<Entity>>(
        `/entities?namespace_id=${encodeURIComponent(nsId)}&is_cerebellum=false&limit=200`,
      );
      setEntities(page.items);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) {
          setIsUnauthorized(true);
          return;
        }
      }
      setErrorMessage(resolveError(t, error));
    } finally {
      setIsLoading(false);
    }
  }, [nsId, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleClone = useCallback(
    async (entity: Entity, payload: ClonePayload) => {
      setCloningId(entity.id);
      setErrorMessage(null);
      try {
        await cloneEntity(entity.id, payload);
        await refresh();
      } catch (error) {
        setErrorMessage(resolveError(t, error, 'clone.error'));
      } finally {
        setCloningId(null);
        setCloneTarget(null);
      }
    },
    [refresh, t],
  );

  if (isUnauthorized) {
    return <Navigate to="/login" replace />;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="ns-entities-title">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div>
            <h1 id="ns-entities-title" className="text-2xl font-semibold text-slate-950">
              {t('nav.entities')}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('namespaces.subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => openOnboarding({ namespaceId: nsId })}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          >
            <Sparkles className="size-4" aria-hidden="true" />
            {t('namespaces.summonEntity')}
          </button>
          <button
            type="button"
            disabled={selectedEntityId === null}
            onClick={() => {
              if (selectedEntityId) openEntityModal(selectedEntityId, 'distill');
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            <FlaskConical className="size-4" aria-hidden="true" />
            {t('namespaces.distillTransmute')}
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

      {isLoading ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-6 py-16 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : null}

      {!isLoading ? (
        <EntitiesList
          entities={entities}
          selectedId={selectedEntityId}
          canClone={canCloneEntity}
          cloningId={cloningId}
          onSelect={setSelectedEntityId}
          onClone={(entity) => setCloneTarget(entity)}
          onOpen={(id) => openEntityModal(id)}
          onOpenDistill={(id) => openEntityModal(id, 'distill')}
          t={t}
        />
      ) : null}

      <CloneDialog
        open={cloneTarget !== null}
        title={t('clone.entity')}
        confirmMessage={t('clone.dialog.confirmEntity', {
          name: cloneTarget?.display_name ?? cloneTarget?.name ?? '',
        })}
        confirmLabel={t('clone.entity')}
        busy={cloneTarget !== null && cloningId === cloneTarget.id}
        onConfirm={(payload) => {
          if (cloneTarget !== null) void handleClone(cloneTarget, payload);
        }}
        onCancel={() => setCloneTarget(null)}
      />
    </section>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function EntitiesList({
  entities,
  selectedId,
  canClone,
  cloningId,
  onSelect,
  onClone,
  onOpen,
  onOpenDistill,
  t,
}: {
  readonly entities: readonly Entity[];
  readonly selectedId: string | null;
  readonly canClone: boolean;
  readonly cloningId: string | null;
  readonly onSelect: (id: string) => void;
  readonly onClone: (entity: Entity) => void;
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
                    {t('namespaces.distillTransmute')}
                  </button>
                  {canClone ? (
                    <button
                      type="button"
                      disabled={cloningId !== null}
                      onClick={(e) => {
                        e.stopPropagation();
                        onClone(entity);
                      }}
                      className="inline-flex items-center gap-1 text-slate-600 hover:text-slate-900 disabled:opacity-50"
                      data-testid={`entity-clone-${entity.id}`}
                      title={t('clone.instancesNotCopied')}
                    >
                      <Copy className="size-3.5" aria-hidden="true" />
                      {cloningId === entity.id ? t('clone.cloning') : t('clone.entity')}
                    </button>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
