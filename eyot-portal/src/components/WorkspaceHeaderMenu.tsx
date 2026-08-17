import { Check, ChevronDown, Pencil, RefreshCw, RotateCw, Trash2 } from 'lucide-react';
import { type ReactElement, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WorkspaceHeaderMenuAction = 'batchRestart' | 'editNameSlug' | 'softDelete' | 'refresh';

export type WorkspaceHeaderMenuProps = {
  /** When > 0, the batch-restart item is enabled and shows a badge. */
  readonly outdatedInstanceCount: number;
  readonly onAction: (action: WorkspaceHeaderMenuAction) => void;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function WorkspaceHeaderMenu({
  outdatedInstanceCount,
  onAction,
}: WorkspaceHeaderMenuProps): ReactElement {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((value) => !value), []);

  // Click-outside-to-close behavior.
  useEffect(() => {
    if (!isOpen) return;
    function handlePointerDown(event: MouseEvent) {
      const node = containerRef.current;
      if (node === null) return;
      if (!node.contains(event.target as Node)) {
        close();
      }
    }
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [isOpen, close]);

  // Escape-to-close behavior.
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      close();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, close]);

  function dispatch(action: WorkspaceHeaderMenuAction) {
    close();
    onAction(action);
  }

  const hasOutdated = outdatedInstanceCount > 0;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={toggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={t('workspaceHeader.menuOpen')}
        data-testid="workspace-header-menu-trigger"
        className={cn(
          'inline-flex size-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors',
          'hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:bg-slate-200',
          isOpen && 'bg-slate-100 text-slate-900',
        )}
      >
        <ChevronDown className="size-4" aria-hidden="true" />
      </button>

      {isOpen ? (
        <div
          role="menu"
          aria-label={t('workspaceHeader.menuAria')}
          data-testid="workspace-header-menu"
          className="absolute right-0 top-full z-30 mt-2 w-64 origin-top-right rounded-lg border border-slate-200 bg-white p-1 shadow-lg ring-1 ring-slate-950/5"
        >
          <MenuItem
            icon={<RotateCw className="size-4" aria-hidden="true" />}
            label={t('workspaceHeader.menuBatchRestart')}
            badge={
              hasOutdated
                ? t('workspaceHeader.menuBatchRestartBadge', {
                    count: outdatedInstanceCount,
                  })
                : null
            }
            enabled={hasOutdated}
            disabledHint={!hasOutdated ? null : null}
            testId="workspace-header-menu-batch-restart"
            onClick={() => dispatch('batchRestart')}
          />
          <MenuDivider />
          <MenuItem
            icon={<Pencil className="size-4" aria-hidden="true" />}
            label={t('workspaceHeader.menuEditNameSlug')}
            testId="workspace-header-menu-edit"
            onClick={() => dispatch('editNameSlug')}
          />
          <MenuItem
            icon={<Trash2 className="size-4" aria-hidden="true" />}
            label={t('workspaceHeader.menuSoftDelete')}
            intent="danger"
            testId="workspace-header-menu-soft-delete"
            onClick={() => dispatch('softDelete')}
          />
          <MenuDivider />
          <MenuItem
            icon={<RefreshCw className="size-4" aria-hidden="true" />}
            label={t('workspaceHeader.menuRefresh')}
            testId="workspace-header-menu-refresh"
            onClick={() => dispatch('refresh')}
          />
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type MenuItemProps = {
  readonly icon: ReactElement;
  readonly label: string;
  readonly badge?: string | null;
  readonly enabled?: boolean;
  readonly disabledHint?: string | null;
  readonly intent?: 'default' | 'danger';
  readonly testId?: string;
  readonly onClick: () => void;
};

function MenuItem({
  icon,
  label,
  badge,
  enabled = true,
  disabledHint,
  intent = 'default',
  testId,
  onClick,
}: MenuItemProps): ReactElement {
  const isDanger = intent === 'danger';
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      disabled={!enabled}
      title={disabledHint ?? undefined}
      data-testid={testId}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
        enabled
          ? isDanger
            ? 'text-red-700 hover:bg-red-50'
            : 'text-slate-700 hover:bg-slate-100'
          : 'cursor-not-allowed text-slate-400 hover:bg-transparent',
      )}
    >
      <span
        className={cn(
          'grid size-7 shrink-0 place-items-center rounded-md',
          isDanger ? 'bg-red-50 text-red-600' : 'bg-slate-100 text-slate-600',
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
      {badge !== undefined && badge !== null ? (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-0.5 font-mono text-xs font-semibold',
            enabled ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-500',
          )}
        >
          {badge}
        </span>
      ) : null}
      {enabled ? <Check className="size-3.5 shrink-0 opacity-0" aria-hidden="true" /> : null}
    </button>
  );
}

function MenuDivider(): ReactElement {
  return <div className="my-1 h-px bg-slate-100" aria-hidden="true" />;
}
