import { Link, MousePointer, Move } from 'lucide-react';
import { type ReactElement, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { type InteractionMode, useSelectedStore } from '@/stores/selected';

type ModeConfig = {
  readonly id: InteractionMode;
  readonly label: string;
  readonly shortcut: 'V' | 'C' | 'M';
  readonly Icon: typeof MousePointer;
};

type TopologyToolbarProps = {
  readonly className?: string;
};

export default function TopologyToolbar({ className }: TopologyToolbarProps): ReactElement {
  const { t } = useTranslation();
  const interactionMode = useSelectedStore((state) => state.interactionMode);
  const setInteractionMode = useSelectedStore((state) => state.setInteractionMode);

  const MODES = useMemo<readonly ModeConfig[]>(
    () => [
      { id: 'select', label: t('topology.selectMode'), shortcut: 'V', Icon: MousePointer },
      { id: 'connect', label: t('topology.connectMode'), shortcut: 'C', Icon: Link },
      { id: 'move', label: t('topology.moveMode'), shortcut: 'M', Icon: Move },
    ],
    [t],
  );

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key;
      if (key === 'v' || key === 'V') setInteractionMode('select');
      else if (key === 'c' || key === 'C') setInteractionMode('connect');
      else if (key === 'm' || key === 'M') setInteractionMode('move');
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setInteractionMode]);

  return (
    <div
      className={cn(
        'sticky top-0 z-20 flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2 sm:px-6',
        className,
      )}
      role="toolbar"
      aria-label={t('topology.toolbarAria')}
      data-testid="topology-toolbar"
    >
      {MODES.map(({ id, label, shortcut, Icon }) => {
        const isActive = interactionMode === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setInteractionMode(id)}
            aria-pressed={isActive}
            data-testid={`topology-toolbar-${id}`}
            data-active={isActive ? 'true' : 'false'}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
              isActive
                ? 'bg-blue-600 text-white'
                : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-100',
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            <span>{label}</span>
            <kbd
              className={cn(
                'ml-1 rounded px-1 py-0.5 font-mono text-[10px] leading-none',
                isActive ? 'bg-blue-500/40 text-blue-50' : 'bg-slate-100 text-slate-500',
              )}
            >
              {shortcut}
            </kbd>
          </button>
        );
      })}
    </div>
  );
}
