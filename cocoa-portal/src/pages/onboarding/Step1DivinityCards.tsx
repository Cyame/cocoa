import {
  AlertCircle,
  Binary,
  Check,
  Compass,
  Filter,
  Flame,
  Layers,
  LoaderCircle,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/lib/api';
import { fetchBaseClasses } from '@/lib/api/onboarding';
import { normalizeBaseClassTags, translateBaseClassTag } from '@/lib/baseClassTags';
import type { BaseClass, JsonObject } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useOnboardingStore } from '@/stores/onboardingStore';

type GroupFilter = 'all' | string;

const INTERNAL_SLUGS = new Set(['cerebellum-baseclass']);
const INTERNAL_TAGS = new Set(['internal', 'system']);

const ICON_FOR_SLUG: Record<string, typeof Compass> = {
  fox: Compass,
  beaver: Flame,
  sparrow: Binary,
  coyote: Layers,
  lion: Sparkles,
};

/** Default tags when API omits them - free-form, not a closed enum. */
const DEFAULT_TAGS_FOR_SLUG: Record<string, readonly string[]> = {
  fox: ['planning'],
  beaver: ['ultraworker', 'execution'],
  sparrow: ['execution'],
  coyote: ['execution'],
  lion: ['delegate', 'planning'],
};

const TAG_CLASSES: Record<string, string> = {
  planning: 'bg-blue-50 text-blue-700 border-blue-200',
  execution: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  review: 'bg-violet-50 text-violet-700 border-violet-200',
  ultraworker: 'bg-orange-50 text-orange-800 border-orange-200',
  scout: 'bg-cyan-50 text-cyan-800 border-cyan-200',
  oracle: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  gate: 'bg-amber-50 text-amber-800 border-amber-200',
  multimodal: 'bg-fuchsia-50 text-fuchsia-800 border-fuchsia-200',
  delegate: 'bg-slate-100 text-slate-700 border-slate-300',
};

const DEFAULT_TAG_CLASS = 'bg-slate-50 text-slate-700 border-slate-200';

function resolveTags(baseClass: BaseClass): readonly string[] {
  const fromApi = normalizeBaseClassTags(baseClass.tags);
  if (fromApi.length > 0) return fromApi;
  return DEFAULT_TAGS_FOR_SLUG[baseClass.slug] ?? [];
}

function isInternalBaseClass(baseClass: BaseClass): boolean {
  if (INTERNAL_SLUGS.has(baseClass.slug)) return true;
  return resolveTags(baseClass).some((tag) => INTERNAL_TAGS.has(tag));
}

function primaryTag(baseClass: BaseClass): string {
  return resolveTags(baseClass)[0] ?? 'untagged';
}

function extractCommands(manifest: JsonObject | null): readonly string[] {
  if (manifest === null) return [];
  // manifest here comes from GET /base-classes — the server merges the
  // junction aggregate into manifest.commands (read-only mirror), never the
  // DB-embedded write truth.
  const value = manifest.commands;
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function extractProvider(manifest: JsonObject | null): string | null {
  if (manifest === null) return null;
  const config = manifest.provider_config;
  if (typeof config === 'object' && config !== null) {
    const type = (config as JsonObject).type;
    if (typeof type === 'string') return type;
  }
  const defaultModel = manifest.default_model;
  if (typeof defaultModel === 'string') return defaultModel;
  return null;
}

type Step1Props = {
  readonly onLoadingChange?: (isLoading: boolean) => void;
  readonly onErrorChange?: (error: string | null) => void;
};

export default function Step1DivinityCards({ onLoadingChange, onErrorChange }: Step1Props) {
  const { t } = useTranslation();
  const selectedBaseClass = useOnboardingStore((state) => state.selectedBaseClass);
  const setSelectedBaseClass = useOnboardingStore((state) => state.setSelectedBaseClass);

  const [classes, setClasses] = useState<readonly BaseClass[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState<GroupFilter>('all');

  useEffect(() => {
    let isActive = true;
    async function load() {
      setIsLoading(true);
      setErrorMessage(null);
      if (onLoadingChange) onLoadingChange(true);
      if (onErrorChange) onErrorChange(null);
      try {
        const items = await fetchBaseClasses();
        if (!isActive) return;
        setClasses(items);
        if (items.length === 0) {
          if (onErrorChange) onErrorChange(t('onboarding.step1.fallbackDisclaimer'));
        }
      } catch (error) {
        if (!isActive) return;
        if (error instanceof ApiError) {
          setErrorMessage(error.message);
          if (onErrorChange) onErrorChange(error.message);
        } else {
          setErrorMessage(t('onboarding.loadBaseClassesFailed'));
          if (onErrorChange) onErrorChange(t('onboarding.loadBaseClassesFailed'));
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
          if (onLoadingChange) onLoadingChange(false);
        }
      }
    }
    void load();
    return () => {
      isActive = false;
    };
  }, [onErrorChange, onLoadingChange, t]);

  const dataSource: readonly BaseClass[] = useMemo(() => {
    const source = classes ?? [];
    return source.filter((entry) => !isInternalBaseClass(entry));
  }, [classes]);

  const availableTags = useMemo(() => {
    const set = new Set<string>();
    for (const entry of dataSource) {
      for (const tag of resolveTags(entry)) {
        if (!INTERNAL_TAGS.has(tag)) set.add(tag);
      }
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [dataSource]);

  const filtered: readonly BaseClass[] = useMemo(() => {
    if (groupFilter === 'all') return dataSource;
    return dataSource.filter((entry) => resolveTags(entry).includes(groupFilter));
  }, [dataSource, groupFilter]);

  const selectedId = selectedBaseClass?.id ?? null;

  const groups: ReadonlyArray<{ readonly id: GroupFilter; readonly label: string }> = [
    { id: 'all', label: t('onboarding.step1.tagFilterAll') },
    ...availableTags.map((tag) => ({ id: tag, label: translateBaseClassTag(tag, t) })),
  ];

  return (
    <div className="space-y-5" data-testid="onboarding-step1">
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-slate-950">{t('onboarding.step1.title')}</h3>
        <p className="text-sm text-slate-500">{t('onboarding.step1.subtitle')}</p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Tag filter">
        {groups.map((group) => {
          const isActive = groupFilter === group.id;
          return (
            <button
              key={group.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setGroupFilter(group.id)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                isActive
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}
            >
              {group.id === 'all' ? <Filter className="size-3.5" aria-hidden="true" /> : null}
              {group.label}
            </button>
          );
        })}
      </div>

      {errorMessage !== null && classes === null ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              setErrorMessage(null);
              setIsLoading(true);
              void (async () => {
                try {
                  const items = await fetchBaseClasses();
                  setClasses(items);
                } catch (error) {
                  setErrorMessage(
                    error instanceof ApiError
                      ? error.message
                      : t('onboarding.loadBaseClassesFailed'),
                  );
                } finally {
                  setIsLoading(false);
                }
              })();
            }}
            className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-white px-2 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
          >
            <RefreshCw className="size-3" aria-hidden="true" />
            {t('common.retry')}
          </button>
        </div>
      ) : null}

      {isLoading && classes === null ? (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-200 bg-slate-50 py-12 text-sm text-slate-500">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </div>
      ) : (
        <fieldset>
          <legend className="sr-only">{t('onboarding.step1.title')}</legend>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((entry) => {
              const isSelected = entry.id === selectedId;
              const Icon = ICON_FOR_SLUG[entry.slug] ?? Compass;
              const tags = resolveTags(entry);
              const lead = primaryTag(entry);
              const commands = extractCommands(entry.manifest);
              const providerInfo = extractProvider(entry.manifest);
              const displayName = t(entry.display_name ?? entry.name, { defaultValue: entry.name });
              return (
                <label
                  key={entry.id}
                  data-testid={`deity-card-${entry.slug}`}
                  className={cn(
                    'flex w-full cursor-pointer flex-col items-start gap-3 rounded-xl border bg-white p-4 text-left shadow-sm transition-[border-color,box-shadow,transform] focus-within:ring-2 focus-within:ring-blue-500',
                    isSelected
                      ? 'border-blue-500 ring-2 ring-blue-500/20 shadow-md -translate-y-0.5'
                      : 'border-slate-200 hover:border-slate-400 hover:shadow-md',
                  )}
                >
                  <input
                    type="radio"
                    name="deity-selection"
                    value={entry.id}
                    checked={isSelected}
                    onChange={() => setSelectedBaseClass(isSelected ? null : entry)}
                    aria-label={displayName}
                    className="sr-only"
                  />
                  <div className="flex w-full items-start justify-between gap-2">
                    <span
                      className={cn(
                        'grid size-9 shrink-0 place-items-center rounded-lg',
                        isSelected ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-700',
                      )}
                    >
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    {isSelected ? (
                      <span className="grid size-5 place-items-center rounded-full bg-blue-600 text-white">
                        <Check className="size-3" aria-hidden="true" />
                      </span>
                    ) : null}
                  </div>

                  <div className="min-w-0">
                    <h4 className="text-base font-semibold text-slate-950">{displayName}</h4>
                    <p className="mt-0.5 font-mono text-xs text-slate-500">{entry.slug}</p>
                  </div>

                  {entry.description !== null ? (
                    <p className="line-clamp-2 text-xs text-slate-600">{entry.description}</p>
                  ) : null}

                  {commands.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {commands.slice(0, 3).map((command) => (
                        <span
                          key={command}
                          className="rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 font-mono text-[11px] text-blue-700"
                        >
                          {command}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className="flex w-full flex-wrap items-center gap-1.5 pt-1">
                    {tags.slice(0, 3).map((tag) => (
                      <span
                        key={tag}
                        className={cn(
                          'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium',
                          TAG_CLASSES[tag] ?? DEFAULT_TAG_CLASS,
                          tag === lead ? 'ring-1 ring-offset-1 ring-slate-300' : '',
                        )}
                      >
                        {translateBaseClassTag(tag, t)}
                      </span>
                    ))}
                    {providerInfo !== null ? (
                      <span
                        className="ml-auto truncate font-mono text-[11px] text-slate-500"
                        title={providerInfo}
                      >
                        {t('onboarding.step1.providerLabel')}: {providerInfo}
                      </span>
                    ) : null}
                  </div>
                </label>
              );
            })}
          </div>
        </fieldset>
      )}

      {selectedBaseClass === null ? (
        <p className="text-xs text-slate-500" aria-live="polite">
          {t('onboarding.step1.selectHint')}
        </p>
      ) : null}
    </div>
  );
}
