import { AlertCircle, CheckCircle2, LoaderCircle, Square, XCircle } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { cancelDeploy, fetchDeploySnapshot, streamDeployProgress } from '@/lib/api/deploy';
import { cn } from '@/lib/utils';
import { useDeployProgressStore } from '@/stores/deployProgressStore';
import { useSessionStore } from '@/stores/session';

/** Client-side deploy watch timeout (matches backend healthz window). */
export const DEPLOY_UI_TIMEOUT_MS = 300_000;

function parseStepNames(message: string | null): readonly string[] | null {
  if (!message) return null;
  try {
    const parsed = JSON.parse(message) as { steps?: string[] };
    if (Array.isArray(parsed.steps) && parsed.steps.every((s) => typeof s === 'string')) {
      return parsed.steps;
    }
  } catch {
    return null;
  }
  return null;
}

export default function DeployProgressFloat() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const token = useSessionStore((s) => s.token);
  const job = useDeployProgressStore((s) => s.job);
  const patch = useDeployProgressStore((s) => s.patch);
  const minimize = useDeployProgressStore((s) => s.minimize);
  const expand = useDeployProgressStore((s) => s.expand);
  const clear = useDeployProgressStore((s) => s.clear);
  const abortRef = useRef<AbortController | null>(null);

  const terminal = job !== null && job.phase !== 'running';

  useEffect(() => {
    if (job === null || job.phase !== 'running') return;
    const recordId = job.recordId;
    const ac = new AbortController();
    abortRef.current = ac;
    let finished = false;

    const timeoutId = window.setTimeout(() => {
      if (finished) return;
      finished = true;
      ac.abort();
      patch({ phase: 'timeout', message: t('deploy.timeout') });
    }, DEPLOY_UI_TIMEOUT_MS);

    const pollSnapshot = async () => {
      try {
        const snap = await fetchDeploySnapshot(recordId);
        if (ac.signal.aborted || finished) return;
        const names = parseStepNames(snap.message);
        if (names !== null) patch({ stepNames: names });
        if (snap.status === 'success') {
          finished = true;
          patch({ phase: 'success', currentStep: 9, stepStatus: 'done' });
          return true;
        }
        if (snap.status === 'failed') {
          finished = true;
          patch({ phase: 'failed', message: snap.message });
          return true;
        }
        if (snap.status === 'cancelled') {
          finished = true;
          patch({ phase: 'cancelled' });
          return true;
        }
      } catch {
        // best-effort
      }
      return false;
    };

    void (async () => {
      // Seed from snapshot (late subscribe / already done).
      if (await pollSnapshot()) {
        window.clearTimeout(timeoutId);
        return;
      }
      try {
        await streamDeployProgress(
          recordId,
          token,
          (frame) => {
            if (finished || ac.signal.aborted) return;
            if (typeof frame.step === 'number') {
              patch({
                currentStep: frame.step,
                stepStatus: frame.status ?? 'running',
                message: frame.message ?? null,
              });
            }
            if (frame.status === 'failed') {
              finished = true;
              patch({ phase: 'failed', message: frame.message ?? t('deploy.failed') });
            } else if (frame.step === 9 && frame.status === 'done') {
              finished = true;
              patch({ phase: 'success', currentStep: 9, stepStatus: 'done' });
            }
          },
          ac.signal,
        );
      } catch {
        if (!finished && !ac.signal.aborted) {
          // Fall back to snapshot polling until timeout.
          const interval = window.setInterval(() => {
            void pollSnapshot().then((done) => {
              if (done) window.clearInterval(interval);
            });
          }, 2000);
          ac.signal.addEventListener('abort', () => window.clearInterval(interval));
        }
      } finally {
        if (finished) window.clearTimeout(timeoutId);
      }
    })();

    return () => {
      window.clearTimeout(timeoutId);
      ac.abort();
    };
  }, [job?.recordId, job?.phase, patch, t, token, job]);

  const steps = useMemo(() => job?.stepNames ?? [], [job?.stepNames]);

  if (job === null) return null;

  if (job.minimized && !terminal) {
    return (
      <button
        type="button"
        onClick={expand}
        data-testid="deploy-progress-minimized"
        className="fixed bottom-4 right-4 z-[70] inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-lg hover:bg-slate-50"
      >
        <LoaderCircle className="size-4 animate-spin text-blue-600" aria-hidden="true" />
        {t('deploy.runningBackground')}
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deploy-progress-title"
      data-testid="deploy-progress-float"
      className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/40 p-0 sm:items-center sm:p-4"
    >
      <div className="flex w-full max-w-md flex-col overflow-hidden rounded-t-xl border border-slate-200 bg-white shadow-2xl sm:rounded-xl">
        <header className="border-b border-slate-200 px-5 py-4">
          <h2 id="deploy-progress-title" className="text-base font-semibold text-slate-950">
            {terminal
              ? job.phase === 'success'
                ? t('deploy.successTitle')
                : job.phase === 'cancelled'
                  ? t('deploy.cancelledTitle')
                  : job.phase === 'timeout'
                    ? t('deploy.timeoutTitle')
                    : t('deploy.failedTitle')
              : t('deploy.runningTitle')}
          </h2>
          <p className="mt-1 text-xs text-slate-500">{t('deploy.subtitle')}</p>
        </header>

        <div className="max-h-[50vh] space-y-2 overflow-y-auto px-5 py-4">
          {steps.map((name, index) => {
            const stepNum = index + 1;
            let state: 'pending' | 'running' | 'done' | 'failed' = 'pending';
            if (job.phase === 'failed' && stepNum === job.currentStep) state = 'failed';
            else if (
              job.currentStep > stepNum ||
              (job.currentStep === stepNum && job.stepStatus === 'done')
            )
              state = 'done';
            else if (job.currentStep === stepNum && job.phase === 'running') state = 'running';
            else if (job.phase === 'success') state = 'done';

            return (
              <div
                key={name}
                className="flex items-center gap-3 rounded-lg border border-slate-100 px-3 py-2 text-sm"
                data-testid={`deploy-step-${stepNum}`}
              >
                {state === 'running' ? (
                  <LoaderCircle className="size-4 shrink-0 animate-spin text-blue-600" />
                ) : state === 'done' ? (
                  <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                ) : state === 'failed' ? (
                  <XCircle className="size-4 shrink-0 text-red-600" />
                ) : (
                  <span className="size-4 shrink-0 rounded-full border border-slate-300" />
                )}
                <span
                  className={cn(
                    'font-mono text-xs',
                    state === 'pending' ? 'text-slate-400' : 'text-slate-800',
                  )}
                >
                  {t(`deploy.steps.${name}`, { defaultValue: name })}
                </span>
              </div>
            );
          })}

          {job.message && (job.phase === 'failed' || job.phase === 'timeout') ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <p className="break-all">{job.message}</p>
            </div>
          ) : null}
        </div>

        <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          {!terminal ? (
            <>
              <button
                type="button"
                onClick={minimize}
                data-testid="deploy-run-background"
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                {t('deploy.runBackground')}
              </button>
              <button
                type="button"
                onClick={() => {
                  void cancelDeploy(job.recordId)
                    .then(() => {
                      abortRef.current?.abort();
                      patch({ phase: 'cancelled' });
                    })
                    .catch(() => {
                      patch({ phase: 'failed', message: t('deploy.cancelFailed') });
                    });
                }}
                data-testid="deploy-cancel"
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-semibold text-red-800 hover:bg-red-100"
              >
                <Square className="size-3.5" aria-hidden="true" />
                {t('deploy.cancel')}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => {
                const workspaceId = job.workspaceId;
                clear();
                navigate(`/workspaces/${encodeURIComponent(workspaceId)}`);
              }}
              data-testid="deploy-start-using"
              className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
            >
              {t('deploy.startUsing')}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
