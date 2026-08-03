import { AlertCircle, Check, ChevronDown, Layers, LoaderCircle } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ApiError } from '@/lib/api';
import { fetchNamespaces, type NamespaceWithStats } from '@/lib/api/namespaces';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/session';

type NamespaceSwitcherProps = {
  readonly orgId: string;
};

/**
 * Sidebar ② namespace switcher (v4.3 H2): lists the org's namespaces, marks
 * the current one, and navigating a selection lands on that namespace's
 * overview route (also syncing currentNamespaceId in the session store).
 */
export default function NamespaceSwitcher({ orgId }: NamespaceSwitcherProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const currentNamespaceId = useSessionStore((state) => state.currentNamespaceId);
  const setCurrentNamespace = useSessionStore((state) => state.setCurrentNamespace);

  const [namespaces, setNamespaces] = useState<readonly NamespaceWithStats[] | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const load = useCallback(async () => {
    if (namespaces !== null) return;
    setLoading(true);
    setError(null);
    try {
      const page = await fetchNamespaces();
      setNamespaces(page.items);
    } catch (loadError) {
      setError(loadError instanceof ApiError ? loadError.message : t('errors.network'));
    } finally {
      setLoading(false);
    }
  }, [namespaces, t]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    function onDocPointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function selectNamespace(nsId: string) {
    setOpen(false);
    if (nsId === currentNamespaceId) return;
    setCurrentNamespace(nsId);
    navigate(`/orgs/${orgId}/namespaces/${nsId}`);
  }

  const current = namespaces?.find((ns) => ns.id === currentNamespaceId) ?? null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={t('nav.currentNamespace')}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={listId}
        data-testid="namespace-switcher"
        className="flex w-full min-w-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        <Layers className="size-4 shrink-0" aria-hidden="true" />
        <span className="truncate">
          {current?.name ??
            (currentNamespaceId !== null ? currentNamespaceId : t('nav.namespaces'))}
        </span>
        <ChevronDown
          className={cn(
            'ml-auto size-3.5 shrink-0 opacity-70 transition-transform',
            open ? 'rotate-180' : '',
          )}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <div
          id={listId}
          data-testid="namespace-switcher-menu"
          className="absolute left-0 z-50 mt-1.5 max-h-72 min-w-[14rem] overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 py-1 text-slate-100 shadow-lg"
        >
          {loading ? (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('orgPicker.loading')}
            </div>
          ) : error !== null ? (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-red-400">
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{error}</span>
            </div>
          ) : (namespaces ?? []).length === 0 ? (
            <div className="px-3 py-2 text-sm text-slate-500">
              {t('dashboard.emptyNamespacesTitle')}
            </div>
          ) : (
            (namespaces ?? []).map((ns) => {
              const selected = ns.id === currentNamespaceId;
              return (
                <button
                  key={ns.id}
                  type="button"
                  data-testid={`namespace-switcher-option-${ns.slug}`}
                  onClick={() => selectNamespace(ns.id)}
                  aria-current={selected ? 'true' : undefined}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors',
                    selected
                      ? 'bg-blue-600 font-medium text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate">{ns.name}</span>
                    <span className="block truncate font-mono text-[10px] opacity-60">
                      {ns.slug}
                    </span>
                  </span>
                  {selected ? <Check className="size-3.5 shrink-0" aria-hidden="true" /> : null}
                </button>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
