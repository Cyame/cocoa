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

export function ModeToolbar(): ReactElement {
  const { t } = useTranslation();
  const interactionMode = useSelectedStore((state) => state.interactionMode);
  const setInteractionMode = useSelectedStore((state) => state.setInteractionMode);
  const modes = useMemo<readonly ModeConfig[]>(
    () => [
      { id: 'select', label: t('topology.selectMode'), shortcut: 'V', Icon: MousePointer },
      { id: 'connect', label: t('topology.connectMode'), shortcut: 'C', Icon: Link },
      { id: 'move', label: t('topology.moveMode'), shortcut: 'M', Icon: Move },
    ],
    [t],
  );

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      )
        return;
      switch (event.key.toLowerCase()) {
        case 'v':
          setInteractionMode('select');
          break;
        case 'c':
          setInteractionMode('connect');
          break;
        case 'm':
          setInteractionMode('move');
          break;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setInteractionMode]);

  return (
    <div
      className="absolute left-4 top-4 z-20 flex rounded-full border border-slate-200 bg-white/95 p-1 shadow-lg backdrop-blur"
      role="radiogroup"
      aria-label={t('topology.toolbarAria')}
      data-testid="topology-toolbar"
    >
      {modes.map(({ id, label, shortcut, Icon }) => {
        const isActive = interactionMode === id;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={isActive}
            disabled={isActive}
            onClick={() => setInteractionMode(id)}
            data-testid={`topology-toolbar-${id}`}
            data-active={isActive ? 'true' : 'false'}
            className={cn(
              'inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
              isActive
                ? 'bg-blue-600 text-white disabled:opacity-100'
                : 'text-slate-600 hover:bg-slate-100',
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">{label}</span>
            <kbd
              className={cn('font-mono text-[10px]', isActive ? 'text-blue-100' : 'text-slate-400')}
            >
              {shortcut}
            </kbd>
          </button>
        );
      })}
    </div>
  );
}
