import { AlertTriangle, FileText, KeyRound, LoaderCircle, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { KnowledgeScope } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useOnboardingStore } from '@/stores/onboardingStore';

type Step3Props = {
  readonly isSubmitting: boolean;
  readonly submitError: string | null;
};

const SCOPE_OPTIONS: ReadonlyArray<{
  readonly value: KnowledgeScope;
  readonly labelKey: 'knowledgeScopeInstance' | 'knowledgeScopeEntity' | 'knowledgeScopeWorkspace';
  readonly helpKey:
    | 'knowledgeScopeInstanceHelp'
    | 'knowledgeScopeEntityHelp'
    | 'knowledgeScopeWorkspaceHelp';
}> = [
  {
    value: 'instance',
    labelKey: 'knowledgeScopeInstance',
    helpKey: 'knowledgeScopeInstanceHelp',
  },
  {
    value: 'entity',
    labelKey: 'knowledgeScopeEntity',
    helpKey: 'knowledgeScopeEntityHelp',
  },
  {
    value: 'workspace',
    labelKey: 'knowledgeScopeWorkspace',
    helpKey: 'knowledgeScopeWorkspaceHelp',
  },
];

export default function Step3KnowledgeConfirm({ isSubmitting, submitError }: Step3Props) {
  const { t } = useTranslation();
  const knowledgeRows = useOnboardingStore((state) => state.knowledgeRows);
  const knowledgeFiles = useOnboardingStore((state) => state.knowledgeFiles);
  const knowledgeScope = useOnboardingStore((state) => state.knowledgeScope);
  const setKnowledgeScope = useOnboardingStore((state) => state.setKnowledgeScope);
  const displayName = useOnboardingStore((state) => state.displayName);

  const trimmedDisplayName = displayName.trim() === '' ? '（未命名）' : displayName.trim();
  const validEnvEntries = knowledgeRows.filter((row) => row.key.trim() !== '');
  const hasKnowledge = validEnvEntries.length > 0 || knowledgeFiles.length > 0;

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
          {t('onboarding.step3.knowledgeSummary')}
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

      <fieldset>
        <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('onboarding.step3.knowledgeScopeHeading')}
        </legend>
        <div className="mt-2 space-y-2">
          {SCOPE_OPTIONS.map((option) => {
            const isChecked = knowledgeScope === option.value;
            const isWorkspace = option.value === 'workspace';
            return (
              <label
                key={option.value}
                className={cn(
                  'flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                  isChecked
                    ? isWorkspace
                      ? 'border-red-400 bg-red-50 text-red-900'
                      : 'border-blue-500 bg-blue-50 text-blue-900'
                    : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
                )}
              >
                <input
                  type="radio"
                  name="knowledge_scope"
                  value={option.value}
                  checked={isChecked}
                  onChange={() => setKnowledgeScope(option.value)}
                  className="mt-0.5 size-4 accent-blue-600"
                />
                <div>
                  <div className="flex items-center gap-1.5">
                    {isWorkspace ? (
                      <ShieldAlert className="size-3.5 text-red-600" aria-hidden="true" />
                    ) : null}
                    <span>{t(`onboarding.step3.${option.labelKey}`)}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {t(`onboarding.step3.${option.helpKey}`)}
                  </p>
                </div>
              </label>
            );
          })}
        </div>
      </fieldset>

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
