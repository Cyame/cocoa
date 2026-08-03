import {
  Bug,
  Building2,
  Dna,
  Fingerprint,
  FlaskConical,
  Globe2,
  Layers,
  LogOut,
  Sparkles,
  User,
  Users,
  Workflow,
} from 'lucide-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, NavLink, Outlet, useLocation, useSearchParams } from 'react-router';
import GlobalModals from '@/components/GlobalModals';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { api } from '@/lib/api';
import type { AuthUserPayload } from '@/lib/types';
import { cn } from '@/lib/utils';
import { APP_VERSION } from '@/lib/version';
import { useSessionStore } from '@/stores/session';

const TAB_IDS = [
  'workspace',
  'base-classes',
  'contracts',
  'entities',
  'instances',
  'genes',
  'capability-market',
  'debug',
] as const;

export type NamespaceTabId = (typeof TAB_IDS)[number];

const DESKTOP_LINK_CLASS =
  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500';

const IDENTITY_LABEL_KEYS: Record<string, string> = {
  system: 'identity.system',
  org: 'identity.org',
  namespace: 'identity.namespace',
  workspace: 'identity.workspace',
  member: 'identity.member',
};

type NavItem =
  | {
      readonly kind: 'tab';
      readonly id: NamespaceTabId;
      readonly labelKey: string;
      readonly Icon: typeof Building2;
    }
  | {
      readonly kind: 'route';
      readonly to: string;
      readonly labelKey: string;
      readonly Icon: typeof Building2;
      readonly match: (pathname: string, tab: string | null) => boolean;
    };

const NAV_ITEMS: readonly NavItem[] = [
  {
    kind: 'route',
    to: '/organization?tab=world',
    labelKey: 'nav.world',
    Icon: Globe2,
    match: (pathname) => pathname.startsWith('/organization'),
  },
  {
    kind: 'route',
    to: '/organization?tab=namespaces',
    labelKey: 'nav.namespace',
    Icon: Layers,
    match: (pathname, tab) => pathname.startsWith('/organization') && tab === 'namespaces',
  },
  { kind: 'tab', id: 'workspace', labelKey: 'nav.workspace', Icon: Building2 },
  { kind: 'tab', id: 'base-classes', labelKey: 'nav.baseClasses', Icon: Sparkles },
  { kind: 'tab', id: 'contracts', labelKey: 'nav.contracts', Icon: Fingerprint },
  { kind: 'tab', id: 'entities', labelKey: 'nav.entities', Icon: Users },
  { kind: 'tab', id: 'instances', labelKey: 'nav.instances', Icon: Workflow },
  { kind: 'tab', id: 'genes', labelKey: 'nav.genes', Icon: Dna },
  { kind: 'tab', id: 'capability-market', labelKey: 'nav.capability', Icon: FlaskConical },
  { kind: 'tab', id: 'debug', labelKey: 'nav.debug', Icon: Bug },
];

export default function AppShell() {
  const { t } = useTranslation();
  const location = useLocation();
  const token = useSessionStore((state) => state.token);
  const user = useSessionStore((state) => state.user);
  const setToken = useSessionStore((state) => state.setToken);
  const clearToken = useSessionStore((state) => state.clearToken);
  const [searchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') ?? 'workspace') as NamespaceTabId;
  const orgTab = searchParams.get('tab');

  useEffect(() => {
    if (token === null) return;
    if (user?.username && user.user_id && user.identity !== undefined) return;
    let cancelled = false;
    void api<AuthUserPayload>('/auth/me')
      .then((me) => {
        if (cancelled) return;
        setToken(token, {
          user_id: me.id,
          username: me.username,
          nickname: me.nickname ?? null,
          email: me.email,
          is_super_admin: me.is_super_admin,
          identity: me.identity ?? null,
          locked_gene_slugs: me.locked_gene_slugs ?? [],
          extra_gene_slugs: me.extra_gene_slugs ?? [],
          token,
        });
      })
      .catch(() => {
        /* keep token; profile hydrate is best-effort */
      });
    return () => {
      cancelled = true;
    };
  }, [token, user?.username, user?.user_id, setToken]);

  if (token === null) {
    return <Navigate to="/login" replace />;
  }

  const identityLabelKey =
    user?.identity && IDENTITY_LABEL_KEYS[user.identity]
      ? IDENTITY_LABEL_KEYS[user.identity]
      : user?.is_super_admin
        ? 'identity.system'
        : 'identity.member';

  function navActive(item: NavItem): boolean {
    if (item.kind === 'tab') {
      return location.pathname.startsWith('/namespaces') && activeTab === item.id;
    }
    // Prefer exact org tab match for 次元; 世界 matches other org tabs.
    if (item.to.includes('tab=namespaces')) {
      return location.pathname.startsWith('/organization') && orgTab === 'namespaces';
    }
    return location.pathname.startsWith('/organization') && orgTab !== 'namespaces';
  }

  return (
    <div className="flex min-h-dvh bg-slate-100 text-slate-950 md:h-dvh md:overflow-hidden">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100 md:flex">
        <div className="flex h-16 items-center gap-3 border-b border-slate-800 px-5">
          <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white">
            <Building2 className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight">{t('common.appName')}</p>
            <p className="truncate text-xs text-slate-400">{t('common.controlStudio')}</p>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            const to = item.kind === 'tab' ? `/namespaces?tab=${item.id}` : item.to;
            const Icon = item.Icon;
            return (
              <NavLink
                key={item.labelKey}
                to={to}
                className={() =>
                  cn(
                    DESKTOP_LINK_CLASS,
                    navActive(item)
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                  )
                }
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                <span className="truncate">{t(item.labelKey)}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="mb-3 flex items-center justify-between gap-2 px-1">
            <LanguageSwitcher variant="sidebar" placement="up" />
            <span className="font-mono text-[11px] text-slate-500">v{APP_VERSION}</span>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:min-h-0">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{t('common.appName')}</p>
            <p className="truncate text-xs text-slate-500">{t('common.controlStudio')}</p>
          </div>

          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Link
              to="/account"
              className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50"
            >
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
                <User className="size-4" aria-hidden="true" />
              </span>
              <div className="hidden min-w-0 sm:block">
                <p className="max-w-48 truncate text-sm font-medium text-slate-800">
                  {user?.nickname?.trim() ||
                    user?.username ||
                    user?.user_id ||
                    t('common.authenticatedUser')}
                </p>
                <p className="text-xs text-slate-500">{t(identityLabelKey)}</p>
                {(user?.extra_gene_slugs ?? []).length > 0 && (
                  <p
                    className="max-w-48 truncate font-mono text-[10px] text-slate-400"
                    title={(user?.extra_gene_slugs ?? []).join(', ')}
                  >
                    {(user?.extra_gene_slugs ?? []).slice(0, 2).join(' · ')}
                    {(user?.extra_gene_slugs ?? []).length > 2
                      ? ` +${(user?.extra_gene_slugs ?? []).length - 2}`
                      : ''}
                  </p>
                )}
              </div>
            </Link>
            <button
              type="button"
              onClick={clearToken}
              className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:bg-slate-200"
              aria-label={t('common.logOut')}
              title={t('common.logOut')}
            >
              <LogOut className="size-4" aria-hidden="true" />
            </button>
          </div>
        </header>

        <nav
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 pt-2 md:hidden"
          aria-label="Primary tabs"
        >
          {NAV_ITEMS.map((item) => {
            const to = item.kind === 'tab' ? `/namespaces?tab=${item.id}` : item.to;
            return (
              <NavLink
                key={item.labelKey}
                to={to}
                className={() =>
                  cn(
                    'shrink-0 rounded-t-lg border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                    navActive(item)
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-transparent text-slate-500 hover:bg-slate-50',
                  )
                }
              >
                {t(item.labelKey)}
              </NavLink>
            );
          })}
        </nav>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <GlobalModals />
    </div>
  );
}
