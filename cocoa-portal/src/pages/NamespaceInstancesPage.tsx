import { AlertCircle, Cpu, LoaderCircle, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useParams } from 'react-router';
import PromoteModal from '@/components/PromoteModal';
import { ApiError, api } from '@/lib/api';
import { type EntityDetail, fetchEntity, promoteEntity } from '@/lib/api/entities';
import { listInstances } from '@/lib/api/instances';
import type { Entity, Instance } from '@/lib/types';
import { useEntityModalStore } from '@/stores/entityModalStore';

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export default function NamespaceInstancesPage() {
  const { t } = useTranslation();
  const { orgId, nsId } = useParams<{ orgId: string; nsId: string }>();

  const [instances, setInstances] = useState<readonly Instance[]>([]);
  const [entities, setEntities] = useState<readonly Entity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUnauthorized, setIsUnauthorized] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<{
    entityId: string;
    instanceId: string;
  } | null>(null);
  const [promoteEntityDetail, setPromoteEntityDetail] = useState<EntityDetail | null>(null);

  const openEntityModal = useEntityModalStore((state) => state.open);

  const refresh = useCallback(async () => {
    if (nsId === undefined) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [entityPage, instancePage] = await Promise.all([
        api<OffsetPage<Entity>>(
          `/entities?namespace_id=${encodeURIComponent(nsId)}&is_cerebellum=false&limit=200`,
        ),
        listInstances({ limit: 200, offset: 0 }),
      ]);
      const nsEntityIds = new Set(entityPage.items.map((e) => e.id));
      setEntities(entityPage.items);
      setInstances(instancePage.items.filter((inst) => nsEntityIds.has(inst.entity_id)));
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
  }, [nsId, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (isUnauthorized) {
    return <Navigate to="/login" replace />;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="ns-instances-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Cpu className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 id="ns-instances-title" className="text-2xl font-semibold text-slate-950">
            {t('namespaces.instancesTitle')}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('namespaces.instancesDetail')}</p>
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
        <InstancesList
          instances={instances}
          entities={entities}
          orgId={orgId ?? ''}
          nsId={nsId ?? ''}
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

function InstancesList({
  instances,
  entities,
  orgId,
  nsId,
  onOpenEntity,
  onPromote,
  t,
}: {
  readonly instances: readonly Instance[];
  readonly entities: readonly Entity[];
  readonly orgId: string;
  readonly nsId: string;
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
          to={`/orgs/${orgId}/namespaces/${nsId}/workspaces`}
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
