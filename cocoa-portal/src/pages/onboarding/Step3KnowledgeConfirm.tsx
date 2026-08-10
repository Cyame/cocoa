import { AlertTriangle, Check, FileText, KeyRound, LoaderCircle } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useOnboardingStore } from '@/stores/onboardingStore';

type Step3Props = {
  readonly isSubmitting: boolean;
  readonly submitError: string | null;
};

export default function Step3KnowledgeConfirm({ isSubmitting, submitError }: Step3Props) {
  const { t } = useTranslation();
  const knowledgeRows = useOnboardingStore((state) => state.knowledgeRows);
  const knowledgeFiles = useOnboardingStore((state) => state.knowledgeFiles);
  const displayName = useOnboardingStore((state) => state.displayName);
  const selectedBaseClass = useOnboardingStore((state) => state.selectedBaseClass);
  const inheritedKnowledge = useOnboardingStore((state) => state.inheritedKnowledge);
  const setInheritedKnowledge = useOnboardingStore((state) => state.setInheritedKnowledge);

  const trimmedDisplayName = displayName.trim() === '' ? '（未命名）' : displayName.trim();
  const validEnvEntries = knowledgeRows.filter((row) => row.key.trim() !== '');
  const hasKnowledge = validEnvEntries.length > 0 || knowledgeFiles.length > 0;

  const availableInherited = useMemo(() => {
    return selectedBaseClass?.has_knowledge ?? [];
  }, [selectedBaseClass?.has_knowledge]);

  function toggleInherited(slug: string) {
    const current = inheritedKnowledge;
    if (current.includes(slug)) {
      setInheritedKnowledge(current.filter((s) => s !== slug));
    } else {
      setInheritedKnowledge([...current, slug]);
    }
  }

  return (
    <div className="space-y-5" data-testid="onboarding-step3">
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-slate-950">{t('onboarding.step3.title')}</h3>
        <p className="text-sm text-slate-500">
          {t('onboarding.step3.subtitle')} · <span className="font-mono">{trimmedDisplayName}</span>
        </p>
      </div>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('onboarding.step3.lineageKnowledge')}
        </h4>
        <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
          {hasKnowledge ? (
            <ul className="space-y-1.5">
              {validEnvEntries.map((row, index) => (
                <li
                  key={row.id}
                  className="flex items-center gap-2 text-sm text-slate-700"
                  data-testid={`step3-env-${index}`}
                >
                  <KeyRound className="size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
                  <span className="font-mono text-xs">
                    {row.key.trim()}={row.value}
                  </span>
                </li>
              ))}
              {knowledgeFiles.map((file, index) => (
                <li
                  key={file.id}
                  className="flex items-center gap-2 text-sm text-slate-700"
                  data-testid={`step3-file-${index}`}
                >
                  <FileText className="size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
                  <span className="truncate">{file.name}</span>
                  <span className="font-mono text-xs text-slate-500">({file.sizeBytes} B)</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-500">{t('onboarding.step3.knowledgeEmpty')}</p>
          )}
        </div>
      </section>

      {availableInherited.length > 0 ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            {t('onboarding.step3.inheritedKnowledge')}
          </h4>
          <p className="mt-1 text-xs text-slate-500">
            {t('onboarding.step3.inheritedKnowledgeHelp')}
          </p>
          <div className="mt-2 space-y-1.5">
            {availableInherited.map((slug) => {
              const isChecked = inheritedKnowledge.includes(slug);
              return (
                <label
                  key={slug}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                    isChecked
                      ? 'border-blue-500 bg-blue-50 text-blue-900'
                      : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
                  )}
                  data-testid={`step3-inherited-${slug}`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleInherited(slug)}
                    className="size-4 rounded accent-blue-600"
                  />
                  <Check
                    className={cn(
                      'size-3.5 shrink-0',
                      isChecked ? 'text-blue-600' : 'text-slate-300',
                    )}
                    aria-hidden="true"
                  />
                  <span className="font-mono text-xs">{slug}</span>
                </label>
              );
            })}
          </div>
        </section>
      ) : null}

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
    </div>
  );
}
