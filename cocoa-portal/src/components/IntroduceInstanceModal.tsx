import { AlertCircle, Cpu, LoaderCircle, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError, api } from '@/lib/api';
import { introduceEntityIntoWorkspace } from '@/lib/api/instances';
import type { Entity } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useDeployProgressStore } from '@/stores/deployProgressStore';

type IntroduceInstanceModalProps = {
  readonly workspaceId: string;
  readonly onClose: () => void;
  readonly onIntroduced: (instanceId: string) => void;
};

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

export default function IntroduceInstanceModal({
  workspaceId,
  onClose,
  onIntroduced,
}: IntroduceInstanceModalProps) {
  const { t } = useTranslation();
  const startDeploy = useDeployProgressStore((s) => s.start);
  const [entities, setEntities] = useState<readonly Entity[]>([]);
  const [entityId, setEntityId] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void api<OffsetPage<Entity>>('/entities?limit=200')
      .then((page) => {
        if (cancelled) return;
        setEntities(page.items);
        if (page.items.length === 1 && page.items[0]) {
          setEntityId(page.items[0].id);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setErrorMessage(error instanceof ApiError ? error.message : t('errors.network'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  async function handleSubmit() {
    if (!entityId || submitting) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const instance = await introduceEntityIntoWorkspace(workspaceId, entityId);
      onIntroduced(instance.id);
      onClose();
      if (instance.deploy_record_id) {
        startDeploy({
          recordId: instance.deploy_record_id,
          instanceId: instance.id,
          workspaceId,
        });
      }
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? error.message : t('workspace.introduceFailed'),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="introduce-instance-title"
      data-testid="introduce-instance-modal"
      className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4"
    >
      <div className="flex w-full max-w-md flex-col overflow-hidden rounded-t-xl border border-slate-200 bg-white shadow-2xl sm:rounded-xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700">
              <Cpu className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 id="introduce-instance-title" className="text-base font-semibold text-slate-950">
                {t('workspace.introduceTitle')}
              </h2>
              <p className="mt-1 text-xs text-slate-500">{t('workspace.introduceDetail')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            className="grid size-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        <div className="space-y-4 px-5 py-4">
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            {t('workspace.introduceEntity')}
            {loading ? (
              <span className="mt-2 flex items-center gap-2 text-sm font-normal normal-case text-slate-500">
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                {t('common.loading')}
              </span>
            ) : (
              <select
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
                data-testid="introduce-entity-select"
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal normal-case text-slate-900"
              >
                <option value="">{t('workspace.introduceEntityPlaceholder')}</option>
                {entities.map((entity) => (
                  <option key={entity.id} value={entity.id}>
                    {entity.display_name ?? entity.name}
                  </option>
                ))}
              </select>
            )}
          </label>

          {errorMessage !== null ? (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <p>{errorMessage}</p>
            </div>
          ) : null}
        </div>

        <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            disabled={!entityId || submitting || loading}
            onClick={() => void handleSubmit()}
            data-testid="introduce-instance-submit"
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-semibold text-white',
              !entityId || submitting || loading
                ? 'cursor-not-allowed bg-slate-300'
                : 'bg-blue-600 hover:bg-blue-700',
            )}
          >
            {submitting ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
            {t('workspace.introduceSubmit')}
          </button>
        </footer>
      </div>
    </div>
  );
}
