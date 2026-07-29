import {
  AlertTriangle,
  Cpu,
  FileText,
  KeyRound,
  LoaderCircle,
  Lock,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { type ChangeEvent, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { EmployeeRank } from '@/lib/types';
import { cn } from '@/lib/utils';
import { isValidSlug, useOnboardingStore } from '@/stores/onboardingStore';

type Step2Props = {
  readonly existingDisplayNames?: readonly string[];
  readonly isSubmitting: boolean;
  readonly submitError: string | null;
};

const RANK_OPTIONS: ReadonlyArray<{
  readonly value: EmployeeRank;
  readonly key: 'rankResearcher' | 'rankIntern';
}> = [
  { value: 'researcher', key: 'rankResearcher' },
  { value: 'intern', key: 'rankIntern' },
];

const MAX_DISPLAY_NAME_LENGTH = 32;

function makeFileId(): string {
  return `file-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function Step2EntityForm({
  existingDisplayNames = [],
  isSubmitting,
  submitError,
}: Step2Props) {
  const { t } = useTranslation();
  const displayName = useOnboardingStore((state) => state.displayName);
  const slug = useOnboardingStore((state) => state.slug);
  const slugTouched = useOnboardingStore((state) => state.slugTouched);
  const rank = useOnboardingStore((state) => state.rank);
  const provider = useOnboardingStore((state) => state.provider);
  const model = useOnboardingStore((state) => state.model);
  const knowledgeRows = useOnboardingStore((state) => state.knowledgeRows);
  const knowledgeFiles = useOnboardingStore((state) => state.knowledgeFiles);
  const selectedBaseClass = useOnboardingStore((state) => state.selectedBaseClass);
  const setDisplayName = useOnboardingStore((state) => state.setDisplayName);
  const setSlug = useOnboardingStore((state) => state.setSlug);
  const setRank = useOnboardingStore((state) => state.setRank);
  const setProvider = useOnboardingStore((state) => state.setProvider);
  const setModel = useOnboardingStore((state) => state.setModel);
  const addKnowledgeRow = useOnboardingStore((state) => state.addKnowledgeRow);
  const updateKnowledgeRow = useOnboardingStore((state) => state.updateKnowledgeRow);
  const removeKnowledgeRow = useOnboardingStore((state) => state.removeKnowledgeRow);
  const addKnowledgeFile = useOnboardingStore((state) => state.addKnowledgeFile);
  const removeKnowledgeFile = useOnboardingStore((state) => state.removeKnowledgeFile);

  const trimmedDisplayName = displayName.trim();
  const trimmedSlug = slug.trim();

  const displayNameError = useMemo<string | null>(() => {
    if (trimmedDisplayName.length === 0) return null;
    if (trimmedDisplayName.length > MAX_DISPLAY_NAME_LENGTH) {
      return t('onboarding.step2.displayNameTooLong');
    }
    if (existingDisplayNames.includes(trimmedDisplayName)) {
      return t('onboarding.step2.displayNameDuplicate');
    }
    return null;
  }, [existingDisplayNames, t, trimmedDisplayName]);

  const slugError = useMemo<string | null>(() => {
    if (!slugTouched && trimmedSlug.length === 0) return null;
    if (trimmedSlug.length === 0) return t('onboarding.step2.slugRequired');
    if (!isValidSlug(trimmedSlug)) return t('onboarding.step2.slugPattern');
    return null;
  }, [slugTouched, t, trimmedSlug]);

  const displayNameTouchedError =
    trimmedDisplayName.length === 0 ? t('onboarding.step2.displayNameRequired') : null;
  const effectiveDisplayNameError = displayNameError ?? displayNameTouchedError;

  const showDisplayNameInvalid = trimmedDisplayName.length > 0 && displayNameError !== null;
  const showSlugInvalid = trimmedSlug.length > 0 && slugError !== null;

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const list = event.currentTarget.files;
    if (list === null) return;
    for (let index = 0; index < list.length; index += 1) {
      const file = list.item(index);
      if (file === null) continue;
      addKnowledgeFile({
        id: makeFileId(),
        name: file.name,
        sizeBytes: file.size,
        file,
      });
    }
    event.currentTarget.value = '';
  }

  const previewProvider = provider.trim() === '' ? 'default' : provider.trim();
  const previewModel = model.trim() === '' ? 'gpt-4o-mini' : model.trim();
  const previewKnowledgeCount = knowledgeRows.filter((row) => row.key.trim() !== '').length;

  return (
    <div className="space-y-5" data-testid="onboarding-step2">
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-slate-950">{t('onboarding.step2.title')}</h3>
        <p className="text-sm text-slate-500">{t('onboarding.step2.subtitle')}</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <form className="space-y-5" noValidate>
          <div>
            <label
              htmlFor="onboarding-display-name"
              className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
            >
              {t('onboarding.step2.displayNameLabel')}
            </label>
            <input
              id="onboarding-display-name"
              name="display_name"
              type="text"
              required
              maxLength={MAX_DISPLAY_NAME_LENGTH}
              value={displayName}
              onChange={(event) => setDisplayName(event.currentTarget.value)}
              placeholder={t('onboarding.step2.displayNamePlaceholder')}
              aria-invalid={effectiveDisplayNameError !== null}
              className={cn(
                'mt-2 w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2',
                showDisplayNameInvalid || effectiveDisplayNameError !== null
                  ? 'border-red-300 focus-visible:ring-red-500'
                  : 'border-slate-300 focus-visible:ring-blue-500',
              )}
            />
            <p className="mt-1.5 text-xs text-slate-500">{t('onboarding.step2.displayNameHelp')}</p>
            {effectiveDisplayNameError !== null && trimmedDisplayName.length > 0 ? (
              <p className="mt-1.5 text-xs text-red-700" role="alert">
                {effectiveDisplayNameError}
              </p>
            ) : null}
          </div>

          <div>
            <label
              htmlFor="onboarding-slug"
              className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
            >
              {t('onboarding.step2.slugLabel')}
            </label>
            <input
              id="onboarding-slug"
              name="slug"
              type="text"
              required
              value={slug}
              onChange={(event) => setSlug(event.currentTarget.value)}
              placeholder={t('onboarding.step2.slugPlaceholder')}
              aria-invalid={showSlugInvalid}
              className={cn(
                'mt-2 w-full rounded-lg border bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2',
                showSlugInvalid
                  ? 'border-red-300 focus-visible:ring-red-500'
                  : 'border-slate-300 focus-visible:ring-blue-500',
              )}
            />
            <p className="mt-1.5 text-xs text-slate-500">{t('onboarding.step2.slugHelp')}</p>
            {showSlugInvalid ? (
              <p className="mt-1.5 text-xs text-red-700" role="alert">
                {slugError}
              </p>
            ) : null}
          </div>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('onboarding.step2.rankLabel')}
            </legend>
            <div className="mt-2 space-y-2">
              {RANK_OPTIONS.map((option) => {
                const isChecked = rank === option.value;
                return (
                  <label
                    key={option.value}
                    className={cn(
                      'flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                      isChecked
                        ? 'border-blue-500 bg-blue-50 text-blue-900'
                        : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
                    )}
                  >
                    <input
                      type="radio"
                      name="rank"
                      value={option.value}
                      checked={isChecked}
                      onChange={() => setRank(option.value)}
                      className="mt-0.5 size-4 accent-blue-600"
                    />
                    <span>{t(`onboarding.step2.${option.key}`)}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="onboarding-provider"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                {t('onboarding.step2.providerLabel')}
              </label>
              <input
                id="onboarding-provider"
                name="provider"
                type="text"
                value={provider}
                onChange={(event) => setProvider(event.currentTarget.value)}
                placeholder={t('onboarding.step2.providerPlaceholder')}
                className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="onboarding-model"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                {t('onboarding.step2.modelLabel')}
              </label>
              <input
                id="onboarding-model"
                name="model"
                type="text"
                value={model}
                onChange={(event) => setModel(event.currentTarget.value)}
                placeholder={t('onboarding.step2.modelPlaceholder')}
                className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                {t('onboarding.step2.knowledgeEnvLabel')}
              </span>
              <button
                type="button"
                onClick={addKnowledgeRow}
                className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <Plus className="size-3" aria-hidden="true" />
                {t('onboarding.step2.knowledgeEnvAdd')}
              </button>
            </div>
            <div className="mt-2 space-y-2">
              {knowledgeRows.length === 0 ? (
                <p className="text-xs text-slate-500">{t('onboarding.step2.knowledgeFileEmpty')}</p>
              ) : (
                knowledgeRows.map((row, index) => (
                  <div key={row.id} className="flex items-center gap-2">
                    <KeyRound className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
                    <input
                      type="text"
                      value={row.key}
                      onChange={(event) =>
                        updateKnowledgeRow(row.id, { key: event.currentTarget.value })
                      }
                      placeholder="KEY"
                      aria-label={`env key ${index + 1}`}
                      className="w-1/3 rounded-md border border-slate-300 bg-white px-2 py-1.5 font-mono text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    />
                    <span className="text-slate-400">=</span>
                    <input
                      type="text"
                      value={row.value}
                      onChange={(event) =>
                        updateKnowledgeRow(row.id, { value: event.currentTarget.value })
                      }
                      placeholder="VALUE"
                      aria-label={`env value ${index + 1}`}
                      className="flex-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 font-mono text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    />
                    <button
                      type="button"
                      onClick={() => removeKnowledgeRow(row.id)}
                      aria-label={`remove env ${index + 1}`}
                      className="grid size-7 place-items-center rounded-md border border-slate-300 text-slate-500 hover:bg-slate-50 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                {t('onboarding.step2.knowledgeFileLabel')}
              </span>
              <label
                htmlFor="onboarding-knowledge-file"
                className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-within:ring-2 focus-within:ring-blue-500"
              >
                <Plus className="size-3" aria-hidden="true" />
                {t('onboarding.step2.knowledgeFileAdd')}
                <input
                  id="onboarding-knowledge-file"
                  name="knowledge_files"
                  type="file"
                  multiple
                  className="sr-only"
                  onChange={handleFileChange}
                />
              </label>
            </div>
            <div className="mt-2 space-y-2">
              {knowledgeFiles.length === 0 ? (
                <p className="text-xs text-slate-500">{t('onboarding.step2.knowledgeFileEmpty')}</p>
              ) : (
                knowledgeFiles.map((file, index) => (
                  <div
                    key={file.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <FileText className="size-4 shrink-0 text-slate-500" aria-hidden="true" />
                      <span className="truncate text-sm text-slate-900">{file.name}</span>
                      <span className="font-mono text-xs text-slate-500">
                        ({formatBytes(file.sizeBytes)})
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeKnowledgeFile(file.id)}
                      aria-label={`remove file ${index + 1}`}
                      className="grid size-7 place-items-center rounded-md text-slate-500 hover:bg-white hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      <X className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div
            className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
            role="note"
          >
            <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>{t('onboarding.step2.freezeWarning')}</span>
          </div>

          {submitError !== null ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>{submitError}</span>
            </div>
          ) : null}

          {isSubmitting ? (
            <div className="flex items-center gap-2 text-xs text-slate-500" aria-live="polite">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('onboarding.step2.summoning')}
            </div>
          ) : null}
        </form>

        <aside className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Sparkles className="size-3.5" aria-hidden="true" />
            Preview
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="font-mono text-xs text-slate-500">
              {selectedBaseClass?.slug ?? 'unknown-deity'}
            </p>
            <p className="mt-1 text-base font-semibold text-slate-950">
              {trimmedDisplayName === '' ? '（未命名眷族）' : trimmedDisplayName}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-blue-50 px-2 py-0.5 font-mono text-[11px] text-blue-700">
                {trimmedSlug === '' ? 'no-slug' : trimmedSlug}
              </span>
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[11px] font-medium',
                  rank === 'researcher'
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-slate-100 text-slate-700',
                )}
              >
                {rank}
              </span>
            </div>
            <dl className="mt-3 space-y-1.5 text-xs text-slate-600">
              <div className="flex items-center justify-between">
                <dt className="text-slate-500">Provider</dt>
                <dd className="font-mono text-slate-900">{previewProvider}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-slate-500">Model</dt>
                <dd className="font-mono text-slate-900">{previewModel}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-slate-500">Knowledge env</dt>
                <dd className="text-slate-900">
                  {previewKnowledgeCount} {previewKnowledgeCount === 1 ? 'entry' : 'entries'}
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-slate-500">Knowledge files</dt>
                <dd className="text-slate-900">{knowledgeFiles.length}</dd>
              </div>
            </dl>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-500">
              <Cpu className="size-3" aria-hidden="true" />
              <span>Phase-15f preview</span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
