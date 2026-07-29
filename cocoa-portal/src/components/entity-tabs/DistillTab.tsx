import { AlertCircle, Check, FlaskConical, LoaderCircle, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityDetail } from '@/lib/api/entities';
import type { MemoryKind } from '@/lib/types';
import { cn } from '@/lib/utils';

const KIND_ORDER: readonly MemoryKind[] = ['experience', 'lesson', 'decision', 'problem'];

type Toast = {
  readonly kind: 'success' | 'error';
  readonly message: string;
};

type DistillTabProps = {
  readonly entity: EntityDetail;
  readonly canTransmute: boolean;
  readonly onPromote: (kinds: readonly MemoryKind[] | null) => Promise<void>;
  readonly onTransmute: (
    targetSlug: string,
    targetName: string,
    kinds: readonly MemoryKind[] | null,
  ) => Promise<void>;
};

export default function DistillTab({
  entity,
  canTransmute,
  onPromote,
  onTransmute,
}: DistillTabProps) {
  const { t } = useTranslation();
  const [promoteKinds, setPromoteKinds] = useState<ReadonlySet<MemoryKind>>(new Set(KIND_ORDER));
  const [transmuteKinds, setTransmuteKinds] = useState<ReadonlySet<MemoryKind>>(
    new Set(KIND_ORDER),
  );

  const [promoting, setPromoting] = useState(false);
  const [transmuteSubmitting, setTransmuteSubmitting] = useState(false);
  const [promotedAt, setPromotedAt] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const [targetSlug, setTargetSlug] = useState('');
  const [targetName, setTargetName] = useState('');
  const [slugError, setSlugError] = useState<string | null>(null);

  const togglePromoteKind = (kind: MemoryKind) => {
    setPromoteKinds((prev) => toggleSet(prev, kind));
  };
  const toggleTransmuteKind = (kind: MemoryKind) => {
    setTransmuteKinds((prev) => toggleSet(prev, kind));
  };

  const promoteSelected = promoteKinds.size === 0 ? null : Array.from(promoteKinds);
  const transmuteSelected = transmuteKinds.size === 0 ? null : Array.from(transmuteKinds);

  const slugPattern = /^[a-z][a-z0-9-]*$/;
  const slugValid = slugPattern.test(targetSlug);
  const slugEmpty = targetSlug.length === 0;
  const nameEmpty = targetName.trim().length === 0;
  const transmuteDisabled =
    !canTransmute || transmuteSubmitting || slugEmpty || !slugValid || nameEmpty;

  async function handlePromote() {
    if (promoting) return;
    setPromoting(true);
    setToast(null);
    try {
      await onPromote(promoteSelected);
      setPromotedAt(new Date().toISOString());
      setToast({
        kind: 'success',
        message: t('entityModal.distillTab.promote.success', { count: promoteKinds.size }),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : t('entityModal.errors.promote');
      setToast({ kind: 'error', message });
    } finally {
      setPromoting(false);
    }
  }

  async function handleTransmute() {
    if (transmuteDisabled) {
      if (slugEmpty) setSlugError(t('entityModal.distillTab.transmute.targetSlugRequired'));
      else if (!slugValid) setSlugError(t('entityModal.distillTab.transmute.targetSlugInvalid'));
      return;
    }
    setTransmuteSubmitting(true);
    setToast(null);
    try {
      await onTransmute(targetSlug, targetName.trim(), transmuteSelected);
      setToast({ kind: 'success', message: t('entityModal.distillTab.transmute.success') });
      setTargetSlug('');
      setTargetName('');
    } catch (error) {
      const message = error instanceof Error ? error.message : t('entityModal.errors.transmute');
      setToast({ kind: 'error', message });
    } finally {
      setTransmuteSubmitting(false);
    }
  }

  return (
    <section aria-labelledby="distill-tab-heading" className="space-y-5">
      <header>
        <h2 id="distill-tab-heading" className="text-sm font-semibold text-slate-900">
          {t('entityModal.tabs.distill')}
        </h2>
        <p className="mt-1 text-xs text-slate-500">{t('entityModal.distillTab.intro')}</p>
      </header>

      {toast ? (
        <div
          role={toast.kind === 'error' ? 'alert' : 'status'}
          data-testid="distill-toast"
          className={cn(
            'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm',
            toast.kind === 'error'
              ? 'border-red-200 bg-red-50 text-red-800'
              : 'border-emerald-200 bg-emerald-50 text-emerald-800',
          )}
        >
          {toast.kind === 'error' ? (
            <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          ) : (
            <Check className="size-4 shrink-0" aria-hidden="true" />
          )}
          <p>{toast.message}</p>
        </div>
      ) : null}

      <article
        aria-labelledby="distill-promote-heading"
        data-testid="distill-promote-section"
        className="overflow-hidden rounded-xl border border-emerald-200 bg-emerald-50/40"
      >
        <header className="flex items-start gap-3 border-b border-emerald-200 px-4 py-3">
          <span className="grid size-9 place-items-center rounded-lg bg-emerald-100 text-emerald-800">
            <Sparkles className="size-4" aria-hidden="true" />
          </span>
          <div>
            <h3 id="distill-promote-heading" className="text-sm font-semibold text-emerald-900">
              {t('entityModal.distillTab.promote.title')}
            </h3>
            <p className="mt-0.5 text-xs text-emerald-900/80">
              {t('entityModal.distillTab.promote.description')}
            </p>
          </div>
        </header>

        <div className="space-y-4 px-4 py-4">
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-emerald-900">
              {t('entityModal.distillTab.promote.kinds')}
            </legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {KIND_ORDER.map((kind) => (
                <KindChip
                  key={kind}
                  kind={kind}
                  selected={promoteKinds.has(kind)}
                  onToggle={() => togglePromoteKind(kind)}
                  accent="emerald"
                />
              ))}
            </div>
          </fieldset>

          <p className="text-xs text-emerald-900/70">
            {t('entityModal.distillTab.promote.stats', {
              total: promoteKinds.size * 5,
              kinds: promoteKinds.size,
            })}
          </p>

          <div className="flex items-center justify-end gap-3">
            {promotedAt !== null ? (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-800">
                <Check className="size-3.5" aria-hidden="true" />
                {t('entityModal.distillTab.promote.alreadyPromoted')}
                <span className="font-mono">{promotedAt.slice(11, 19)}</span>
              </span>
            ) : null}
            <button
              type="button"
              onClick={handlePromote}
              disabled={promoting || promotedAt !== null}
              data-testid="distill-promote-submit"
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
                promoting || promotedAt !== null
                  ? 'cursor-not-allowed bg-emerald-100 text-emerald-500'
                  : 'bg-emerald-600 text-white hover:bg-emerald-700 active:bg-emerald-800',
              )}
            >
              {promoting ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Sparkles className="size-4" aria-hidden="true" />
              )}
              {promoting
                ? t('entityModal.distillTab.promote.submitting')
                : t('entityModal.distillTab.promote.submit')}
            </button>
          </div>
        </div>
      </article>

      <article
        aria-labelledby="distill-transmute-heading"
        data-testid="distill-transmute-section"
        className={cn(
          'overflow-hidden rounded-xl border',
          canTransmute ? 'border-purple-200 bg-purple-50/40' : 'border-slate-200 bg-slate-50',
        )}
      >
        <header className="flex items-start gap-3 border-b border-inherit px-4 py-3">
          <span
            className={cn(
              'grid size-9 place-items-center rounded-lg',
              canTransmute ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-500',
            )}
          >
            <FlaskConical className="size-4" aria-hidden="true" />
          </span>
          <div>
            <h3
              id="distill-transmute-heading"
              className={cn(
                'text-sm font-semibold',
                canTransmute ? 'text-purple-900' : 'text-slate-700',
              )}
            >
              {t('entityModal.distillTab.transmute.title')}
            </h3>
            <p
              className={cn(
                'mt-0.5 text-xs',
                canTransmute ? 'text-purple-900/80' : 'text-slate-500',
              )}
            >
              {canTransmute
                ? t('entityModal.distillTab.transmute.description')
                : t('entityModal.errors.permission', {
                    cap: 'can_transmute_entity',
                  })}
            </p>
          </div>
        </header>

        <div className="space-y-4 px-4 py-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <label
                htmlFor="distill-transmute-slug"
                className="block text-xs font-semibold uppercase tracking-wide text-purple-900"
              >
                {t('entityModal.distillTab.transmute.targetSlug')}
              </label>
              <input
                id="distill-transmute-slug"
                type="text"
                value={targetSlug}
                disabled={!canTransmute}
                onChange={(e) => {
                  setTargetSlug(e.target.value);
                  setSlugError(null);
                }}
                placeholder={t('entityModal.distillTab.transmute.targetSlugPlaceholder')}
                data-testid="distill-transmute-slug"
                className={cn(
                  'w-full rounded-lg border bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm focus-visible:outline-none focus-visible:ring-2',
                  slugError || (!slugValid && !slugEmpty)
                    ? 'border-red-300 focus-visible:ring-red-500'
                    : 'border-slate-300 focus-visible:ring-purple-500',
                  !canTransmute && 'cursor-not-allowed bg-slate-50 text-slate-500',
                )}
              />
              {slugError ? (
                <p role="alert" className="text-xs text-red-700">
                  {slugError}
                </p>
              ) : !slugValid && !slugEmpty ? (
                <p role="alert" className="text-xs text-red-700">
                  {t('entityModal.distillTab.transmute.targetSlugInvalid')}
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <label
                htmlFor="distill-transmute-name"
                className="block text-xs font-semibold uppercase tracking-wide text-purple-900"
              >
                {t('entityModal.distillTab.transmute.targetName')}
              </label>
              <input
                id="distill-transmute-name"
                type="text"
                value={targetName}
                disabled={!canTransmute}
                onChange={(e) => setTargetName(e.target.value)}
                placeholder={t('entityModal.distillTab.transmute.targetNamePlaceholder')}
                data-testid="distill-transmute-name"
                className={cn(
                  'w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus-visible:outline-none focus-visible:ring-2',
                  'border-slate-300 focus-visible:ring-purple-500',
                  !canTransmute && 'cursor-not-allowed bg-slate-50 text-slate-500',
                )}
              />
              {nameEmpty ? (
                <p role="alert" className="text-xs text-red-700">
                  {t('entityModal.distillTab.transmute.targetNameRequired')}
                </p>
              ) : null}
            </div>
          </div>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-purple-900">
              {t('entityModal.distillTab.transmute.kinds')}
            </legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {KIND_ORDER.map((kind) => (
                <KindChip
                  key={kind}
                  kind={kind}
                  selected={transmuteKinds.has(kind)}
                  onToggle={() => toggleTransmuteKind(kind)}
                  accent="purple"
                />
              ))}
            </div>
          </fieldset>

          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleTransmute}
              disabled={!canTransmute || transmuteDisabled}
              data-testid="distill-transmute-submit"
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2',
                !canTransmute || transmuteDisabled
                  ? 'cursor-not-allowed bg-purple-100 text-purple-500'
                  : 'bg-purple-600 text-white hover:bg-purple-700 active:bg-purple-800 focus-visible:ring-purple-500',
              )}
            >
              {transmuteSubmitting ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <FlaskConical className="size-4" aria-hidden="true" />
              )}
              {transmuteSubmitting
                ? t('entityModal.distillTab.transmute.submitting')
                : t('entityModal.distillTab.transmute.submit')}
            </button>
          </div>
        </div>
      </article>

      <p className="text-xs text-slate-500" data-testid="distill-entity-id">
        {entity.slug}
      </p>
    </section>
  );
}

function KindChip({
  kind,
  selected,
  onToggle,
  accent,
}: {
  readonly kind: MemoryKind;
  readonly selected: boolean;
  readonly onToggle: () => void;
  readonly accent: 'emerald' | 'purple';
}) {
  const { t } = useTranslation();
  const labelMap: Readonly<Record<MemoryKind, string>> = {
    experience: t('learning.experience'),
    lesson: t('learning.lesson'),
    decision: t('learning.decision'),
    problem: t('learning.problem'),
  };
  return (
    <label
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
        selected
          ? accent === 'emerald'
            ? 'border-emerald-500 bg-emerald-50 text-emerald-900'
            : 'border-purple-500 bg-purple-50 text-purple-900'
          : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
      )}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className={cn('size-4', accent === 'emerald' ? 'accent-emerald-600' : 'accent-purple-600')}
        data-testid={`distill-kind-${kind}`}
      />
      {labelMap[kind]}
    </label>
  );
}

function toggleSet(set: ReadonlySet<MemoryKind>, value: MemoryKind): Set<MemoryKind> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}
