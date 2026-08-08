import { AlertCircle, Check, ChevronDown, Globe2, LoaderCircle } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { fetchOrganizations } from '@/lib/api/organizations';
import { resolveError } from '@/lib/apiError';
import type { Organization } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useSelectedStore } from '@/stores/selected';
import { useSessionStore } from '@/stores/session';

/**
 * Minimal dirty-topology proxy for the org-switch confirm (v4.3 B5).
 * selected.ts has no persisted dirty flag — a non-null workspaceId means an
 * IDE is currently open whose local selection / interaction state would be
 * lost on an org switch. PB-2 replaces this with a real per-workspace flag.
 */
function hasDirtyTopology(): boolean {
  return useSelectedStore.getState().workspaceId !== null;
}

type OrgSwitcherProps = {
  readonly variant?: 'header' | 'sidebar';
};

export default function OrgSwitcher({ variant = 'header' }: OrgSwitcherProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const currentOrgId = useSessionStore((state) => state.currentOrgId);
  const setCurrentOrg = useSessionStore((state) => state.setCurrentOrg);

  const [orgs, setOrgs] = useState<readonly Organization[] | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const load = useCallback(async () => {
    if (orgs !== null) return;
    setLoading(true);
    setError(null);
    try {
      const page = await fetchOrganizations();
      if (!Array.isArray(page.items)) {
        // Same OffsetPage contract guard as OrgPickerPage.
        setError(t('errors.invalidResponse'));
        return;
      }
      setOrgs(page.items);
    } catch (loadError) {
      setError(resolveError(t, loadError));
    } finally {
      setLoading(false);
    }
  }, [orgs, t]);

  useEffect(() => {
    void load();
  }, [load]);

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

  function selectOrg(orgId: string) {
    setOpen(false);
    if (orgId === currentOrgId) return;
    if (hasDirtyTopology() && !window.confirm(t('orgPicker.switchDirtyConfirm'))) return;
    // B5: always land on the new org's Dashboard; the URL becomes the new
    // org context (X-Organization-Id follows via setCurrentOrg).
    setCurrentOrg(orgId);
    navigate(`/orgs/${orgId}`);
  }

  const current = orgs?.find((org) => org.id === currentOrgId) ?? null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={t('orgPicker.switcherLabel')}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={listId}
        data-testid="org-switcher"
        className={cn(
          'inline-flex min-w-0 max-w-52 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
          variant === 'header'
            ? 'border border-slate-200 bg-white text-slate-800 hover:bg-slate-100'
            : 'w-full text-slate-200 hover:bg-slate-800',
        )}
      >
        <Globe2 className="size-4 shrink-0" aria-hidden="true" />
        <span className="truncate">
          {current?.name ??
            (currentOrgId !== null ? currentOrgId : t('orgPicker.switcherPlaceholder'))}
        </span>
        <ChevronDown
          className={cn(
            'size-3.5 shrink-0 opacity-70 transition-transform',
            open ? 'rotate-180' : '',
          )}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <div
          id={listId}
          data-testid="org-switcher-menu"
          className={cn(
            'absolute z-50 mt-1.5 min-w-[13rem] max-w-72 overflow-hidden rounded-lg border py-1 shadow-lg',
            variant === 'header'
              ? 'right-0 border-slate-200 bg-white text-slate-900'
              : 'left-0 border-slate-700 bg-slate-900 text-slate-100',
          )}
        >
          {loading ? (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              {t('orgPicker.loading')}
            </div>
          ) : error !== null ? (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-red-600">
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{error}</span>
            </div>
          ) : (orgs ?? []).length === 0 ? (
            <div className="px-3 py-2 text-sm text-slate-500">{t('orgPicker.switcherEmpty')}</div>
          ) : (
            (orgs ?? []).map((org) => {
              const selected = org.id === currentOrgId;
              return (
                <button
                  key={org.id}
                  type="button"
                  data-testid={`org-switcher-option-${org.slug}`}
                  onClick={() => selectOrg(org.id)}
                  aria-current={selected ? 'true' : undefined}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors',
                    variant === 'header'
                      ? selected
                        ? 'bg-blue-50 font-medium text-blue-800'
                        : 'text-slate-700 hover:bg-slate-50'
                      : selected
                        ? 'bg-blue-600 font-medium text-white'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate">{org.name}</span>
                    <span className="block truncate font-mono text-[10px] opacity-60">
                      {org.slug}
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
