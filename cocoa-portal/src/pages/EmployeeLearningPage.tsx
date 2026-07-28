import {
  AlertTriangle,
  Badge as BadgeIcon,
  BookOpen,
  FlaskConical,
  Lightbulb,
  LoaderCircle,
  Sparkles,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type {
  DistillRequest,
  DistillResultOut,
  Employee,
  MemoryKind,
  MemorySummaryOut,
} from '@/lib/types';
import { cn } from '@/lib/utils';

const SLUG_PATTERN = /^[a-z][a-z0-9-]*$/;
const LESSON_PREVIEW_LENGTH = 80;

function truncateLesson(content: string): string {
  if (content.length <= LESSON_PREVIEW_LENGTH) return content;
  return `${content.slice(0, LESSON_PREVIEW_LENGTH)}...`;
}

export default function EmployeeLearningPage() {
  const { t } = useTranslation();
  const { employeeId } = useParams<{ employeeId: string }>();

  const MEMORY_KIND_OPTIONS = useMemo<
    ReadonlyArray<{
      readonly value: MemoryKind;
      readonly label: string;
      readonly Icon: typeof FlaskConical;
    }>
  >(
    () => [
      { value: 'experience', label: t('learning.experience'), Icon: FlaskConical },
      { value: 'lesson', label: t('learning.lesson'), Icon: Lightbulb },
      { value: 'decision', label: t('learning.decision'), Icon: BadgeIcon },
      { value: 'problem', label: t('learning.problem'), Icon: AlertTriangle },
    ],
    [t],
  );
  const [summary, setSummary] = useState<MemorySummaryOut | null>(null);
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [targetSkillSlug, setTargetSkillSlug] = useState('');
  const [targetPresetName, setTargetPresetName] = useState('');
  const [selectedKinds, setSelectedKinds] = useState<ReadonlySet<MemoryKind>>(new Set());
  const [sourcePresetSlug, setSourcePresetSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [distillResult, setDistillResult] = useState<DistillResultOut | null>(null);

  useEffect(() => {
    if (employeeId === undefined) return;
    let isActive = true;

    async function loadSummary() {
      setIsLoading(true);
      setSummaryError(null);
      try {
        const id = employeeId as string;
        const [summaryResponse, employeeResponse] = await Promise.all([
          api<MemorySummaryOut>(`/learning/memories/${encodeURIComponent(id)}/summary`),
          api<Employee>(`/employees/${encodeURIComponent(id)}`).catch(() => null),
        ]);
        if (isActive) {
          setSummary(summaryResponse);
          setEmployee(employeeResponse);
        }
      } catch (error) {
        if (error instanceof ApiError) {
          if (isActive) setSummaryError(error.message);
          return;
        }
        throw error;
      } finally {
        if (isActive) setIsLoading(false);
      }
    }

    void loadSummary();
    return () => {
      isActive = false;
    };
  }, [employeeId]);

  const isSlugValid = useMemo(() => SLUG_PATTERN.test(targetSkillSlug), [targetSkillSlug]);
  const slugErrorMessage = useMemo(() => {
    if (!slugTouched && targetSkillSlug === '') return null;
    if (targetSkillSlug === '') return t('learning.skillSlugRequired');
    if (!isSlugValid) {
      return t('learning.skillSlugPattern');
    }
    return null;
  }, [targetSkillSlug, isSlugValid, slugTouched, t]);
  const canSubmit = isSlugValid && targetSkillSlug.length > 0 && !isSubmitting;

  function toggleKind(kind: MemoryKind) {
    setSelectedKinds((previous) => {
      const next = new Set(previous);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
      }
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (employeeId === undefined || !canSubmit) return;

    setSlugTouched(true);
    setIsSubmitting(true);
    setSubmitError(null);

    const requestBody: DistillRequest = {
      target_skill_slug: targetSkillSlug,
      memory_kind_filter: selectedKinds.size > 0 ? Array.from(selectedKinds) : null,
      source_preset_slug: sourcePresetSlug.trim() === '' ? null : sourcePresetSlug.trim(),
      target_preset_name: targetPresetName.trim() === '' ? null : targetPresetName.trim(),
    };

    try {
      const result = await api<DistillResultOut>(
        `/learning/employees/${encodeURIComponent(employeeId)}/distill`,
        {
          method: 'POST',
          body: JSON.stringify(requestBody),
        },
      );
      setDistillResult(result);
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        setIsSubmitting(false);
        return;
      }
      throw error;
    } finally {
      setIsSubmitting(false);
    }
  }

  if (employeeId === undefined) {
    return <p className="p-6 text-sm text-red-700">{t('learning.employeeIdMissing')}</p>;
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="learning-title">
      <header className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white">
            <BookOpen className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-xs text-slate-500">{employee?.slug ?? employeeId}</p>
            <h1
              id="learning-title"
              className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl"
            >
              {t('learning.title')}
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Review aggregated memory and distill a reusable skill into a new preset.
            </p>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-sm font-semibold text-slate-900">{t('learning.memorySummary')}</h2>

          {summaryError !== null ? (
            <div
              role="alert"
              className="mt-4 flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <p>{summaryError}</p>
            </div>
          ) : null}

          {isLoading ? (
            <div className="mt-6 flex min-h-32 items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
              {t('common.loading')} summary
            </div>
          ) : null}

          {!isLoading && summary !== null ? (
            <>
              <dl className="mt-4 grid grid-cols-2 gap-3">
                {MEMORY_KIND_OPTIONS.map(({ value, label, Icon }) => (
                  <div
                    key={value}
                    className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5"
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-md bg-white text-slate-600 shadow-sm">
                      <Icon className="size-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                        {label}
                      </dt>
                      <dd
                        className="text-lg font-semibold tabular-nums text-slate-900"
                        data-testid={`count-${value}`}
                      >
                        {summary.aggregated_counts[value]}
                      </dd>
                    </div>
                  </div>
                ))}
              </dl>

              <div className="mt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Sample lessons
                </h3>
                {summary.sample_lessons.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-500">{t('learning.noEntries')}</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {summary.sample_lessons.slice(0, 5).map((lesson) => (
                      <li
                        key={lesson}
                        className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-5 text-slate-700"
                      >
                        {truncateLesson(lesson)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : null}
        </article>

        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
              <Sparkles className="size-4" aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                {t('learning.distillHeading')}
              </h2>
              <p className="text-xs text-slate-500">
                Aggregate memories into a new employee preset.
              </p>
            </div>
          </div>

          <form className="mt-5 space-y-5" onSubmit={handleSubmit} noValidate>
            <div>
              <label
                htmlFor="target-skill-slug"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                {t('learning.skillSlugLabel')}
              </label>
              <input
                id="target-skill-slug"
                name="target_skill_slug"
                type="text"
                required
                value={targetSkillSlug}
                onChange={(event) => setTargetSkillSlug(event.target.value)}
                onBlur={() => setSlugTouched(true)}
                placeholder={t('learning.skillSlugPlaceholder')}
                pattern="[a-z][a-z0-9-]*"
                aria-invalid={slugErrorMessage !== null}
                aria-describedby={slugErrorMessage !== null ? 'skill-slug-error' : undefined}
                className={cn(
                  'mt-2 w-full rounded-lg border bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2',
                  slugErrorMessage !== null
                    ? 'border-red-300 focus-visible:ring-red-500'
                    : 'border-slate-300 focus-visible:ring-blue-500',
                )}
              />
              {slugErrorMessage !== null ? (
                <p id="skill-slug-error" role="alert" className="mt-2 text-xs text-red-700">
                  {slugErrorMessage}
                </p>
              ) : null}
            </div>

            <div>
              <label
                htmlFor="target-preset-name"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                Preset name <span className="font-normal text-slate-400">(optional)</span>
              </label>
              <input
                id="target-preset-name"
                name="target_preset_name"
                type="text"
                value={targetPresetName}
                onChange={(event) => setTargetPresetName(event.target.value)}
                placeholder="Skill: code-review"
                className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>

            <fieldset>
              <legend className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Memory kinds <span className="font-normal text-slate-400">(all if none)</span>
              </legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {MEMORY_KIND_OPTIONS.map(({ value, label }) => (
                  <label
                    key={value}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                      selectedKinds.has(value)
                        ? 'border-blue-500 bg-blue-50 text-blue-900'
                        : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedKinds.has(value)}
                      onChange={() => toggleKind(value)}
                      className="size-4 accent-blue-600"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>

            <div>
              <label
                htmlFor="source-preset-slug"
                className="block text-xs font-semibold uppercase tracking-wide text-slate-600"
              >
                Source preset slug <span className="font-normal text-slate-400">(optional)</span>
              </label>
              <input
                id="source-preset-slug"
                name="source_preset_slug"
                type="text"
                value={sourcePresetSlug}
                onChange={(event) => setSourcePresetSlug(event.target.value)}
                placeholder={employee?.preset_slug ?? 'base'}
                className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>

            {submitError !== null ? (
              <div
                role="alert"
                className="flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
              >
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <p>{submitError}</p>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!canSubmit}
              className={cn(
                'inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                canSubmit
                  ? 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800'
                  : 'cursor-not-allowed bg-slate-200 text-slate-500',
              )}
            >
              {isSubmitting ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Sparkles className="size-4" aria-hidden="true" />
              )}
              {isSubmitting ? `${t('learning.distillSubmit')}...` : t('learning.distillSubmit')}
            </button>
          </form>
        </article>
      </div>

      {distillResult !== null ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="distill-result-title"
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
        >
          <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="grid size-10 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
                  <Sparkles className="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h2 id="distill-result-title" className="text-base font-semibold text-slate-950">
                    Skill distilled
                  </h2>
                  <p className="text-xs text-slate-500">A new preset is ready to use.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDistillResult(null)}
                aria-label="Close"
                className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </div>

            <dl className="mt-5 space-y-3">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Preset slug
                </dt>
                <dd className="mt-1 font-mono text-sm text-slate-900">
                  {distillResult.new_preset_slug}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Preset name
                </dt>
                <dd className="mt-1 text-sm text-slate-900">{distillResult.new_preset_name}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Manifest preview
                </dt>
                <dd className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                    <span className="font-semibold text-slate-500">Model</span>
                    <span className="font-mono text-slate-900">
                      {distillResult.manifest_preview.model}
                    </span>
                    <span className="font-semibold text-slate-500">Prompt</span>
                    <span className="line-clamp-2 text-slate-900">
                      {distillResult.manifest_preview.prompt}
                    </span>
                    <span className="font-semibold text-slate-500">Skills</span>
                    <span className="font-mono text-slate-900">
                      {distillResult.manifest_preview.skills.length === 0
                        ? '(none)'
                        : distillResult.manifest_preview.skills.join(', ')}
                    </span>
                    <span className="font-semibold text-slate-500">Tools</span>
                    <span className="font-mono text-slate-900">
                      {distillResult.manifest_preview.tools.length === 0
                        ? '(none)'
                        : distillResult.manifest_preview.tools.join(', ')}
                    </span>
                    <span className="font-semibold text-slate-500">Commands</span>
                    <span className="font-mono text-slate-900">
                      {distillResult.manifest_preview.commands.length === 0
                        ? '(none)'
                        : distillResult.manifest_preview.commands.join(', ')}
                    </span>
                  </div>
                </dd>
              </div>
            </dl>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setDistillResult(null)}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                Close
              </button>
              <Link
                to={`/employee-presets/${encodeURIComponent(distillResult.new_preset_slug)}`}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <BookOpen className="size-4" aria-hidden="true" />
                View preset
              </Link>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
