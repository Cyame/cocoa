import { useTranslation } from 'react-i18next';
import type { JsonObject } from '@/lib/types';

/** Known subagent capability IDs and their i18n keys. */
const CAPABILITY_IDS = [
  'intent',
  'architecture',
  'quality',
  'explore',
  'research',
  'vision',
] as const;

export type SubagentCapabilityId = (typeof CAPABILITY_IDS)[number];

/**
 * Extract the enabled subagent capability list from a manifest JSON object.
 * Returns an empty array if the manifest has no subagent_strategy or enabled list.
 */
export function extractSubagentCapabilities(
  manifest: JsonObject | null | undefined,
): readonly SubagentCapabilityId[] {
  if (manifest === null || manifest === undefined || typeof manifest !== 'object') return [];
  const strategy = manifest.subagent_strategy;
  if (strategy === null || strategy === undefined || typeof strategy !== 'object') return [];
  const enabled = (strategy as JsonObject).enabled;
  if (!Array.isArray(enabled)) return [];
  return enabled.filter(
    (id): id is SubagentCapabilityId =>
      typeof id === 'string' && (CAPABILITY_IDS as readonly string[]).includes(id),
  );
}

type SubagentChipsProps = {
  readonly capabilities: readonly SubagentCapabilityId[];
};

/** Render subagent capability chips. Display-only, no interaction. */
export default function SubagentChips({ capabilities }: SubagentChipsProps) {
  const { t } = useTranslation();
  if (capabilities.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <p
        className="text-xs font-semibold uppercase tracking-wide text-slate-500"
        data-testid="subagent-chips-heading"
      >
        {t('subagent.heading')}
      </p>
      <ul
        className="flex flex-wrap gap-1.5"
        data-testid="subagent-chips"
        aria-label={t('subagent.heading')}
      >
        {capabilities.map((cap) => (
          <li
            key={cap}
            data-testid={`subagent-chip-${cap}`}
            className="inline-flex items-center rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-800"
          >
            {t(`subagent.${cap}`)}
          </li>
        ))}
      </ul>
    </div>
  );
}
