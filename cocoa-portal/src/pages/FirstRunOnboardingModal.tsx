import { ArrowLeft, ArrowRight, LoaderCircle, Sparkles, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/lib/api';
import { summonEntity } from '@/lib/api/onboarding';
import type { Employee } from '@/lib/types';
import { cn } from '@/lib/utils';
import Step1DivinityCards from '@/pages/onboarding/Step1DivinityCards';
import Step2EntityForm from '@/pages/onboarding/Step2EntityForm';
import Step3KnowledgeConfirm from '@/pages/onboarding/Step3KnowledgeConfirm';
import { isValidSlug, TOTAL_ONBOARDING_STEPS, useOnboardingStore } from '@/stores/onboardingStore';

type FirstRunOnboardingModalProps = {
  readonly existingDisplayNames?: readonly string[];
  readonly onClose: (reason: 'dismissed' | 'completed' | 'skipped') => void;
};

type StepStatus = 'idle' | 'submitting' | 'success' | 'error';

const NETWORK_RETRYABLE_STATUSES = new Set([0, 408, 425, 429, 500, 502, 503, 504]);

function networkLikeError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  if (NETWORK_RETRYABLE_STATUSES.has(error.status)) return true;
  return error.status >= 500;
}

export default function FirstRunOnboardingModal({
  existingDisplayNames = [],
  onClose,
}: FirstRunOnboardingModalProps) {
  const { t } = useTranslation();

  const step = useOnboardingStore((state) => state.step);
  const selectedBaseClass = useOnboardingStore((state) => state.selectedBaseClass);
  const displayName = useOnboardingStore((state) => state.displayName);
  const slug = useOnboardingStore((state) => state.slug);
  const next = useOnboardingStore((state) => state.next);
  const back = useOnboardingStore((state) => state.back);
  const setSubmitError = useOnboardingStore((state) => state.setSubmitError);
  const buildPayload = useOnboardingStore((state) => state.buildPayload);
  const reset = useOnboardingStore((state) => state.reset);

  const [submitStatus, setSubmitStatus] = useState<StepStatus>('idle');
  const [submitErrorMessage, setSubmitErrorMessage] = useState<string | null>(null);
  const [completedEmployee, setCompletedEmployee] = useState<Employee | null>(null);

  useEffect(() => {
    return () => {
      reset();
    };
  }, [reset]);

  const trimmedDisplayName = displayName.trim();
  const trimmedSlug = slug.trim();
  const canAdvanceFromStep1 = selectedBaseClass !== null;
  const canAdvanceFromStep2 =
    trimmedDisplayName.length > 0 &&
    trimmedDisplayName.length <= 32 &&
    trimmedSlug.length > 0 &&
    isValidSlug(trimmedSlug) &&
    !existingDisplayNames.includes(trimmedDisplayName);

  const canAdvanceFromStep3 = submitStatus !== 'submitting';

  const canGoNext = useMemo(() => {
    if (step === 1) return canAdvanceFromStep1;
    if (step === 2) return canAdvanceFromStep2;
    return canAdvanceFromStep3;
  }, [canAdvanceFromStep1, canAdvanceFromStep2, canAdvanceFromStep3, step]);

  const handleBackdropActivate = useCallback(() => {
    if (submitStatus === 'submitting') return;
    onClose('dismissed');
  }, [onClose, submitStatus]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (submitStatus === 'submitting') return;
        onClose('dismissed');
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, submitStatus]);

  async function handleNext() {
    if (!canGoNext) return;
    setSubmitErrorMessage(null);
    setSubmitError(null);
    if (step === 2) {
      const slugError =
        trimmedSlug.length === 0 || !isValidSlug(trimmedSlug)
          ? t('onboarding.step2.slugPattern')
          : null;
      const displayError =
        trimmedDisplayName.length === 0
          ? t('onboarding.step2.displayNameRequired')
          : trimmedDisplayName.length > 32
            ? t('onboarding.step2.displayNameTooLong')
            : existingDisplayNames.includes(trimmedDisplayName)
              ? t('onboarding.step2.displayNameDuplicate')
              : null;
      if (slugError !== null || displayError !== null) {
        setSubmitErrorMessage(slugError ?? displayError);
        return;
      }
    }
    if (step < TOTAL_ONBOARDING_STEPS) {
      next();
      return;
    }
    await handleSubmit();
  }

  async function handleSubmit() {
    setSubmitStatus('submitting');
    setSubmitErrorMessage(null);
    setSubmitError(null);
    const payload = buildPayload();
    try {
      const employee = await summonEntity(payload);
      setCompletedEmployee(employee);
      setSubmitStatus('success');
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitErrorMessage(error.message);
        if (networkLikeError(error)) {
          setSubmitError(t('onboarding.networkError'));
        } else if (error.status === 409) {
          setSubmitError(t('onboarding.step2.submitFailed'));
        } else {
          setSubmitError(t('onboarding.unexpectedError'));
        }
      } else {
        setSubmitErrorMessage(t('errors.network'));
        setSubmitError(t('onboarding.networkError'));
      }
      setSubmitStatus('error');
    }
  }

  function handleSkip() {
    if (submitStatus === 'submitting') return;
    onClose('skipped');
  }

  function handleClose() {
    if (submitStatus === 'submitting') return;
    onClose('dismissed');
  }

  const stepTitle = useMemo(() => {
    if (step === 1) return t('onboarding.step1.title');
    if (step === 2) return t('onboarding.step2.title');
    return t('onboarding.step3.title');
  }, [step, t]);

  const isFinalStep = step === TOTAL_ONBOARDING_STEPS;
  const isSubmitting = submitStatus === 'submitting';

  if (submitStatus === 'success' && completedEmployee !== null) {
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-success-title"
        data-testid="onboarding-success"
        className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
      >
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-2xl">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
              <Sparkles className="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 id="onboarding-success-title" className="text-base font-semibold text-slate-950">
                {t('onboarding.step3.successTitle')}
              </h2>
              <p className="text-xs text-slate-500">{t('onboarding.step3.successDetail')}</p>
            </div>
          </div>
          <dl className="mt-5 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Display name</dt>
              <dd className="text-slate-900">{completedEmployee.display_name ?? '—'}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Slug</dt>
              <dd className="font-mono text-slate-900">{completedEmployee.slug}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Rank</dt>
              <dd className="text-slate-900">{completedEmployee.rank}</dd>
            </div>
          </dl>
          <button
            type="button"
            onClick={() => onClose('completed')}
            className="mt-6 inline-flex w-full items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {t('common.confirm')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 p-0 md:items-center md:p-4"
      data-testid="onboarding-modal"
    >
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={handleBackdropActivate}
        className="absolute inset-0 cursor-default"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-modal-title"
        className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl md:rounded-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-blue-600 text-white">
              <Sparkles className="size-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">
                {t('common.appName')}
              </p>
              <h2
                id="onboarding-modal-title"
                className="mt-0.5 text-base font-semibold text-slate-950 sm:text-lg"
              >
                {stepTitle}
              </h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'inline-flex items-center rounded-full px-2.5 py-1 font-mono text-[11px] font-medium',
                step === TOTAL_ONBOARDING_STEPS
                  ? 'bg-blue-100 text-blue-700 ring-2 ring-blue-500/30'
                  : 'bg-slate-100 text-slate-600',
              )}
              data-testid="step-indicator"
            >
              {t('onboarding.stepIndicator', {
                current: step,
                total: TOTAL_ONBOARDING_STEPS,
              })}
            </span>
            <button
              type="button"
              onClick={handleClose}
              aria-label={t('onboarding.close')}
              disabled={isSubmitting}
              className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {step === 1 ? <Step1DivinityCards /> : null}
          {step === 2 ? (
            <Step2EntityForm
              existingDisplayNames={existingDisplayNames}
              isSubmitting={isSubmitting}
              submitError={submitErrorMessage}
            />
          ) : null}
          {step === 3 ? (
            <Step3KnowledgeConfirm isSubmitting={isSubmitting} submitError={submitErrorMessage} />
          ) : null}
        </div>

        <footer className="flex flex-col-reverse gap-2 border-t border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div className="flex items-center gap-2">
            {step > 1 ? (
              <button
                type="button"
                onClick={back}
                disabled={isSubmitting}
                data-testid="onboarding-back"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ArrowLeft className="size-4" aria-hidden="true" />
                {t('onboarding.back')}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSkip}
                disabled={isSubmitting}
                className="text-sm font-medium text-slate-500 underline-offset-4 hover:underline"
              >
                {t('onboarding.dismiss')}
              </button>
            )}
            {isFinalStep ? (
              <button
                type="button"
                onClick={() => onClose('skipped')}
                disabled={isSubmitting}
                className="text-sm font-medium text-slate-500 underline-offset-4 hover:underline"
              >
                {t('onboarding.skipNextTime')}
              </button>
            ) : null}
          </div>

          <button
            type="button"
            onClick={() => void handleNext()}
            disabled={!canGoNext || isSubmitting}
            data-testid="onboarding-next"
            className={cn(
              'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
              canGoNext && !isSubmitting
                ? 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800'
                : 'cursor-not-allowed bg-slate-200 text-slate-500',
            )}
          >
            {isSubmitting ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : isFinalStep ? (
              <Sparkles className="size-4" aria-hidden="true" />
            ) : (
              <ArrowRight className="size-4" aria-hidden="true" />
            )}
            {isSubmitting
              ? t('onboarding.step2.summoning')
              : isFinalStep
                ? t('onboarding.createAndSpawn')
                : t('onboarding.next')}
          </button>
        </footer>
      </div>
    </div>
  );
}
