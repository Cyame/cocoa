import { AlertCircle, Info, LoaderCircle, Sparkles, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityDetail, PromotePayload } from '@/lib/api/entities';
import { resolveError } from '@/lib/apiError';
import { cn } from '@/lib/utils';

type PromoteModalProps = {
  readonly entity: EntityDetail;
  readonly instanceCount?: number;
  readonly fromInstanceId?: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (payload: PromotePayload) => Promise<void>;
};

export default function PromoteModal({
  entity,
  instanceCount = 0,
  fromInstanceId = null,
  onClose,
  onSubmit,
}: PromoteModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'update' | 'fork'>('update');
  const [forkName, setForkName] = useState('');
  const [forkSlug, setForkSlug] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const slugPattern = /^[a-z][a-z0-9-]*$/;
  const forkSlugValid = slugPattern.test(forkSlug.trim());
  const forkReady =
    mode === 'update' ||
    (forkName.trim().length > 0 && forkSlug.trim().length > 0 && forkSlugValid);

  const ctaLabel = useMemo(
    () => (mode === 'update' ? t('promoteModal.confirmUpdate') : t('promoteModal.confirmFork')),
    [mode, t],
  );

  async function handleSubmit() {
    if (!forkReady || submitting) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const payload: PromotePayload =
        mode === 'fork'
          ? {
              mode: 'fork',
              from_instance_id: fromInstanceId,
              new_entity_name: forkName.trim(),
              new_entity_slug: forkSlug.trim(),
            }
          : { mode: 'update', from_instance_id: fromInstanceId };
      await onSubmit(payload);
      onClose();
    } catch (error) {
      setErrorMessage(resolveError(t, error, 'entityModal.errors.promote'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="promote-modal-title"
      data-testid="promote-modal"
      className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4"
    >
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-t-xl border border-slate-200 bg-white shadow-2xl sm:rounded-xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
              <Sparkles className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 id="promote-modal-title" className="text-base font-semibold text-slate-950">
                {t('promoteModal.title')}
              </h2>
              <p className="mt-1 text-xs text-slate-500">{entity.display_name ?? entity.name}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('promoteModal.close')}
            className="grid size-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('promoteModal.modeLabel')}
            </legend>
            <div className="mt-2 space-y-2">
              {(['update', 'fork'] as const).map((value) => (
                <label
                  key={value}
                  className={cn(
                    'flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2.5 text-sm',
                    mode === value
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-900'
                      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                  )}
                >
                  <input
                    type="radio"
                    name="promote-mode"
                    value={value}
                    checked={mode === value}
                    onChange={() => setMode(value)}
                    className="mt-0.5 size-4 accent-emerald-600"
                    data-testid={`promote-mode-${value}`}
                  />
                  <span>
                    <span className="font-medium">{t(`promoteModal.mode.${value}.label`)}</span>
                    <span className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                      <Info className="size-3 shrink-0" aria-hidden="true" />
                      {t(`promoteModal.mode.${value}.hint`)}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {mode === 'update' ? (
            <div
              className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900"
              data-testid="promote-impact-copy"
            >
              {t('promoteModal.updateImpact', {
                name: entity.display_name ?? entity.name,
                count: instanceCount,
              })}
            </div>
          ) : (
            <div className="grid gap-3">
              <div>
                <label
                  htmlFor="promote-fork-name"
                  className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  {t('promoteModal.forkName')}
                </label>
                <input
                  id="promote-fork-name"
                  type="text"
                  value={forkName}
                  onChange={(e) => setForkName(e.target.value)}
                  data-testid="promote-fork-name"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                />
              </div>
              <div>
                <label
                  htmlFor="promote-fork-slug"
                  className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  {t('promoteModal.forkSlug')}
                </label>
                <input
                  id="promote-fork-slug"
                  type="text"
                  value={forkSlug}
                  onChange={(e) => setForkSlug(e.target.value)}
                  data-testid="promote-fork-slug"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                />
                {forkSlug.trim().length > 0 && !forkSlugValid ? (
                  <p role="alert" className="mt-1 text-xs text-red-700">
                    {t('entityModal.distillTab.transmute.targetSlugInvalid')}
                  </p>
                ) : null}
              </div>
              <p className="text-xs text-slate-500">{t('promoteModal.forkNote')}</p>
            </div>
          )}

          {errorMessage !== null ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <p>{errorMessage}</p>
            </div>
          ) : null}
        </div>

        <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            {t('promoteModal.cancel')}
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!forkReady || submitting}
            data-testid="promote-modal-submit"
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white',
              forkReady && !submitting
                ? 'bg-emerald-600 hover:bg-emerald-700'
                : 'cursor-not-allowed bg-emerald-200',
            )}
          >
            {submitting ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            {submitting ? t('promoteModal.submitting') : ctaLabel}
          </button>
        </footer>
      </div>
    </div>
  );
}
