import { AlertCircle, FlaskConical, LoaderCircle, X } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityDetail } from '@/lib/api/entities';
import { resolveError } from '@/lib/apiError';
import type { MemoryKind } from '@/lib/types';
import { cn } from '@/lib/utils';

const KIND_ORDER: readonly MemoryKind[] = [
  'experience',
  'lesson',
  'decision',
  'problem',
  'notepad',
];

type TransmuteModalProps = {
  readonly entity: EntityDetail;
  readonly onClose: () => void;
  readonly onSubmit: (
    targetSlug: string,
    targetName: string,
    kinds: readonly MemoryKind[] | null,
  ) => Promise<void>;
};

export default function TransmuteModal({ entity, onClose, onSubmit }: TransmuteModalProps) {
  const { t } = useTranslation();
  const [targetSlug, setTargetSlug] = useState('');
  const [targetName, setTargetName] = useState('');
  const [transmuteKinds, setTransmuteKinds] = useState<ReadonlySet<MemoryKind>>(
    new Set(KIND_ORDER),
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const slugPattern = /^[a-z][a-z0-9-]*$/;
  const slugValid = slugPattern.test(targetSlug.trim());
  const ready = targetName.trim().length > 0 && targetSlug.trim().length > 0 && slugValid;

  function toggleKind(kind: MemoryKind) {
    setTransmuteKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  async function handleSubmit() {
    if (!ready || submitting) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const kinds = transmuteKinds.size === 0 ? null : Array.from(transmuteKinds);
      await onSubmit(targetSlug.trim(), targetName.trim(), kinds);
      onClose();
    } catch (error) {
      setErrorMessage(resolveError(t, error, 'entityModal.errors.transmute'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="transmute-modal-title"
      data-testid="transmute-modal"
      className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4"
    >
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-t-xl border border-slate-200 bg-white shadow-2xl sm:rounded-xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-purple-50 text-purple-700">
              <FlaskConical className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 id="transmute-modal-title" className="text-base font-semibold text-slate-950">
                {t('transmuteModal.title')}
              </h2>
              <p className="mt-1 text-xs text-slate-500">{entity.display_name ?? entity.name}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('transmuteModal.close')}
            className="grid size-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div
            className="rounded-lg border border-purple-200 bg-purple-50 px-3 py-2.5 text-xs text-purple-900"
            data-testid="transmute-confirm-copy"
          >
            {t('transmuteModal.confirmCopy')}
          </div>

          <div className="grid gap-3">
            <div>
              <label
                htmlFor="transmute-modal-slug"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                {t('entityModal.distillTab.transmute.targetSlug')}
              </label>
              <input
                id="transmute-modal-slug"
                type="text"
                value={targetSlug}
                onChange={(e) => setTargetSlug(e.target.value)}
                data-testid="transmute-modal-slug"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
              />
            </div>
            <div>
              <label
                htmlFor="transmute-modal-name"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                {t('entityModal.distillTab.transmute.targetName')}
              </label>
              <input
                id="transmute-modal-name"
                type="text"
                value={targetName}
                onChange={(e) => setTargetName(e.target.value)}
                data-testid="transmute-modal-name"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
              />
            </div>
          </div>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('entityModal.distillTab.transmute.kinds')}
            </legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {KIND_ORDER.map((kind) => (
                <label
                  key={kind}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm',
                    transmuteKinds.has(kind)
                      ? 'border-purple-500 bg-purple-50 text-purple-900'
                      : 'border-slate-200 bg-white text-slate-700',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={transmuteKinds.has(kind)}
                    onChange={() => toggleKind(kind)}
                    className="size-4 accent-purple-600"
                    data-testid={`transmute-kind-${kind}`}
                  />
                  {t(`learning.${kind}`)}
                </label>
              ))}
            </div>
          </fieldset>

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
            {t('transmuteModal.cancel')}
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!ready || submitting}
            data-testid="transmute-modal-submit"
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white',
              ready && !submitting
                ? 'bg-purple-600 hover:bg-purple-700'
                : 'cursor-not-allowed bg-purple-200',
            )}
          >
            {submitting ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <FlaskConical className="size-4" aria-hidden="true" />
            )}
            {submitting ? t('transmuteModal.submitting') : t('transmuteModal.confirm')}
          </button>
        </footer>
      </div>
    </div>
  );
}
