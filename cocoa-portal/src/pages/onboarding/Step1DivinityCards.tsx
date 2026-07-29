import {
  AlertCircle,
  BadgeCheck,
  Binary,
  BookOpen,
  Check,
  Compass,
  Eye,
  Filter,
  Flame,
  Layers,
  LoaderCircle,
  RefreshCw,
  ScanEye,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/lib/api';
import { fetchBaseClasses } from '@/lib/api/onboarding';
import type { BaseClass, JsonObject } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useOnboardingStore } from '@/stores/onboardingStore';

type GroupId = 'plan' | 'execute' | 'review';

const FALLBACK_BASE_CLASSES: readonly BaseClass[] = [
  {
    id: 'fallback-mi-shi',
    slug: 'mi-shi',
    name: 'mi-shi',
    display_name: '密士',
    description: '战略规划师：拆解目标、规划路径。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/plan', '/decompose', '/prioritize'] },
    version: '1.0',
    tags: ['plan'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-huan-ling',
    slug: 'huan-ling',
    name: 'huan-ling',
    display_name: '唤灵',
    description: '意图分析师：澄清诉求、提出方案。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/analyze', '/clarify', '/propose'] },
    version: '1.0',
    tags: ['plan'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-an-xing',
    slug: 'an-xing',
    name: 'an-xing',
    display_name: '暗行',
    description: '单兵全栈：独立完成端到端任务。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/plan', '/execute', '/build'] },
    version: '1.0',
    tags: ['execute'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-an-ying',
    slug: 'an-ying',
    name: 'an-ying',
    display_name: '暗影',
    description: '初级执行：快速、低成本完成任务。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/execute', '/build', '/test'] },
    version: '1.0',
    tags: ['execute'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-zhu-jin',
    slug: 'zhu-jin',
    name: 'zhu-jin',
    display_name: '铸金',
    description: '自主深度工作者：以目标为驱动持续推进。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/execute', '/build', '/test'] },
    version: '1.0',
    tags: ['execute'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-ling-shi',
    slug: 'ling-shi',
    name: 'ling-shi',
    display_name: '灵视',
    description: '只读架构 / 调试：分析与预测。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/analyze', '/predict', '/review'] },
    version: '1.0',
    tags: ['review'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-heng-pan',
    slug: 'heng-pan',
    name: 'heng-pan',
    display_name: '衡判',
    description: '质量门禁：审查、批准或驳回。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/review', '/approve', '/reject'] },
    version: '1.0',
    tags: ['review'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-you-hun',
    slug: 'you-hun',
    name: 'you-hun',
    display_name: '游魂',
    description: '代码库检索 / 探索。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/search', '/survey', '/report'] },
    version: '1.0',
    tags: ['review'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-qian-zhi',
    slug: 'qian-zhi',
    name: 'qian-zhi',
    display_name: '潜知',
    description: '外部参考 / 多仓库 / 文档研究。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/search', '/reference', '/survey'] },
    version: '1.0',
    tags: ['review'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-bai-tong',
    slug: 'bai-tong',
    name: 'bai-tong',
    display_name: '百瞳',
    description: '视觉 / 媒体 / 音频分析。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/look', '/analyze', '/describe'] },
    version: '1.0',
    tags: ['review'],
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'fallback-jiu-ri',
    slug: 'jiu-ri',
    name: 'jiu-ri',
    display_name: '旧日',
    description: '顶层调度 / 监督：委派与监控。',
    manifest: { default_model: 'gpt-4o-mini', commands: ['/delegate', '/monitor', '/approve'] },
    version: '1.0',
    tags: ['plan'],
    created_at: '2026-07-01T00:00:00Z',
  },
];

const ICON_FOR_SLUG: Record<string, typeof Compass> = {
  'mi-shi': Compass,
  'huan-ling': Wand2,
  'an-xing': Flame,
  'an-ying': Binary,
  'zhu-jin': Layers,
  'ling-shi': ScanEye,
  'heng-pan': BadgeCheck,
  'you-hun': Filter,
  'qian-zhi': BookOpen,
  'bai-tong': Eye,
  'jiu-ri': Sparkles,
};

const GROUP_FOR_SLUG: Record<string, GroupId> = {
  'mi-shi': 'plan',
  'huan-ling': 'plan',
  'jiu-ri': 'plan',
  'an-xing': 'execute',
  'an-ying': 'execute',
  'zhu-jin': 'execute',
  'ling-shi': 'review',
  'heng-pan': 'review',
  'you-hun': 'review',
  'qian-zhi': 'review',
  'bai-tong': 'review',
};

const GROUP_CLASSES: Record<GroupId, string> = {
  plan: 'bg-blue-50 text-blue-700 border-blue-200',
  execute: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  review: 'bg-violet-50 text-violet-700 border-violet-200',
};

const GROUP_ICONS: Record<GroupId, typeof Compass> = {
  plan: Compass,
  execute: Flame,
  review: Eye,
};

type GroupFilter = 'all' | GroupId;

function normalizeTags(tags: readonly string[] | null): readonly string[] {
  if (tags === null) return [];
  return tags.map((tag) => tag.toLowerCase());
}

function classifyGroup(baseClass: BaseClass): GroupId {
  const slugGroup = GROUP_FOR_SLUG[baseClass.slug];
  if (slugGroup !== undefined) return slugGroup;
  const tags = normalizeTags(baseClass.tags);
  if (tags.includes('plan')) return 'plan';
  if (tags.includes('execute')) return 'execute';
  return 'review';
}

function extractCommands(manifest: JsonObject | null): readonly string[] {
  if (manifest === null) return [];
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
    if (classes !== null && classes.length > 0) return classes;
    return FALLBACK_BASE_CLASSES;
  }, [classes]);

  const filtered: readonly BaseClass[] = useMemo(() => {
    if (groupFilter === 'all') return dataSource;
    return dataSource.filter((entry) => classifyGroup(entry) === groupFilter);
  }, [dataSource, groupFilter]);

  const selectedId = selectedBaseClass?.id ?? null;

  const groups: ReadonlyArray<{ readonly id: GroupFilter; readonly label: string }> = [
    { id: 'all', label: t('onboarding.step1.groupAll') },
    { id: 'plan', label: t('onboarding.step1.groupPlan') },
    { id: 'execute', label: t('onboarding.step1.groupExecute') },
    { id: 'review', label: t('onboarding.step1.groupReview') },
  ];

  return (
    <div className="space-y-5" data-testid="onboarding-step1">
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-slate-950">{t('onboarding.step1.title')}</h3>
        <p className="text-sm text-slate-500">{t('onboarding.step1.subtitle')}</p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Group filter">
        {groups.map((group) => {
          const Icon = group.id === 'all' ? Filter : GROUP_ICONS[group.id];
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
              <Icon className="size-3.5" aria-hidden="true" />
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
              const groupId = classifyGroup(entry);
              const GroupIcon = GROUP_ICONS[groupId];
              const commands = extractCommands(entry.manifest);
              const providerInfo = extractProvider(entry.manifest);
              const displayName = entry.display_name ?? entry.name;
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

                  <div className="flex w-full items-center justify-between gap-2 pt-1">
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
                        GROUP_CLASSES[groupId],
                      )}
                    >
                      <GroupIcon className="size-3" aria-hidden="true" />
                      {groupId}
                    </span>
                    {providerInfo !== null ? (
                      <span
                        className="truncate font-mono text-[11px] text-slate-500"
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
