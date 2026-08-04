import {
  BookOpen,
  Bug,
  Building2,
  Dna,
  Fingerprint,
  FlaskConical,
  Layers,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
  User,
  UserRound,
  Users,
  Workflow,
} from 'lucide-react';
import { useEffect, useLayoutEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, NavLink, Outlet, useLocation, useParams } from 'react-router';
import GlobalModals from '@/components/GlobalModals';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import NamespaceSwitcher from '@/components/NamespaceSwitcher';
import OrgSwitcher from '@/components/OrgSwitcher';
import StatusBar from '@/components/StatusBar';
import { api } from '@/lib/api';
import type { AuthUserPayload } from '@/lib/types';
import { cn } from '@/lib/utils';
import { APP_VERSION } from '@/lib/version';
import { useSessionStore } from '@/stores/session';

const DESKTOP_LINK_CLASS =
  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500';

const IDENTITY_LABEL_KEYS: Record<string, string> = {
  system: 'identity.system',
  org: 'identity.org',
  namespace: 'identity.namespace',
  workspace: 'identity.workspace',
  member: 'identity.member',
};

type NavItem = {
  readonly to: string;
  readonly labelKey: string;
  readonly Icon: typeof Building2;
  /** Exact pathname match (children stay unhighlighted); prefix match by default. */
  readonly exact?: boolean;
};

/** ① World section — rendered when an org context is active. */
function worldNavItems(orgId: string): readonly NavItem[] {
  return [
    { to: `/orgs/${orgId}`, labelKey: 'nav.dashboard', Icon: LayoutDashboard, exact: true },
    { to: `/orgs/${orgId}/settings`, labelKey: 'nav.settings', Icon: Settings },
    { to: `/orgs/${orgId}/members`, labelKey: 'nav.members', Icon: UserRound },
    { to: `/orgs/${orgId}/base-classes`, labelKey: 'nav.divinity', Icon: Sparkles },
    { to: `/orgs/${orgId}/capabilities`, labelKey: 'nav.capabilities', Icon: FlaskConical },
    { to: `/orgs/${orgId}/genes`, labelKey: 'nav.genes', Icon: Dna },
    { to: `/orgs/${orgId}/knowledge`, labelKey: 'nav.knowledge', Icon: BookOpen },
    { to: `/orgs/${orgId}/namespaces`, labelKey: 'nav.namespaces', Icon: Layers, exact: true },
    { to: `/orgs/${orgId}/debug`, labelKey: 'nav.debug', Icon: Bug },
  ];
}

/** ② Current namespace section — rendered only when a namespace is active. */
function namespaceNavItems(orgId: string, namespaceId: string): readonly NavItem[] {
  return [
    {
      to: `/orgs/${orgId}/namespaces/${namespaceId}/workspaces`,
      labelKey: 'nav.workspaces',
      Icon: Building2,
    },
    {
      to: `/orgs/${orgId}/namespaces/${namespaceId}/entities`,
      labelKey: 'nav.entities',
      Icon: Users,
    },
    {
      to: `/orgs/${orgId}/namespaces/${namespaceId}/instances`,
      labelKey: 'nav.instances',
      Icon: Workflow,
    },
    {
      to: `/orgs/${orgId}/namespaces/${namespaceId}/contracts`,
      labelKey: 'nav.contracts',
      Icon: Fingerprint,
    },
  ];
}

function navActive(item: NavItem, pathname: string): boolean {
  if (item.exact === true) return pathname === item.to;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

/** Extract the namespace id from a canonical /orgs/:orgId/namespaces/:nsId/… path. */
function namespaceIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/orgs\/[^/]+\/namespaces\/([^/]+)/);
  return match?.[1] ?? null;
}

export default function AppShell() {
  const { t } = useTranslation();
  const location = useLocation();
  const { orgId } = useParams<{ orgId: string }>();
  const token = useSessionStore((state) => state.token);
  const user = useSessionStore((state) => state.user);
  const currentOrgId = useSessionStore((state) => state.currentOrgId);
  const currentNamespaceId = useSessionStore((state) => state.currentNamespaceId);
  const setToken = useSessionStore((state) => state.setToken);
  const setCurrentOrg = useSessionStore((state) => state.setCurrentOrg);
  const setCurrentNamespace = useSessionStore((state) => state.setCurrentNamespace);
  const clearToken = useSessionStore((state) => state.clearToken);

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
  }, [token, user?.username, user?.user_id, user?.identity, setToken]);

  // B1 stale-state guard: entering /orgs/:orgId must sync currentOrgId BEFORE
  // children's data effects run. useLayoutEffect completes before the passive
  // phase, so fetch calls (which read the live store for X-Organization-Id)
  // always observe the correct org header.
  useLayoutEffect(() => {
    if (orgId === undefined || orgId === currentOrgId) return;
    setCurrentOrg(orgId);
  }, [orgId, currentOrgId, setCurrentOrg]);

  // Namespace context follows the path: /orgs/:orgId/namespaces/:nsId/… sets
  // it; org-level routes clear it (namespaces are org-scoped).
  useLayoutEffect(() => {
    const nsId = namespaceIdFromPath(location.pathname);
    if (nsId === currentNamespaceId) return;
    setCurrentNamespace(nsId);
  }, [location.pathname, currentNamespaceId, setCurrentNamespace]);

  if (token === null) {
    return <Navigate to="/login" replace />;
  }

  const identityLabelKey =
    user?.identity && IDENTITY_LABEL_KEYS[user.identity]
      ? IDENTITY_LABEL_KEYS[user.identity]
      : user?.is_super_admin
        ? 'identity.system'
        : 'identity.member';

  // The route param is authoritative once the shell mounts; currentOrgId
  // catches the first-paint gap before the layout effect lands.
  const activeOrgId = orgId ?? currentOrgId;
  // Same first-paint consideration for the namespace section.
  const nsIdFromPath = namespaceIdFromPath(location.pathname);
  const activeNamespaceId = nsIdFromPath ?? currentNamespaceId;

  const worldItems = activeOrgId !== null ? worldNavItems(activeOrgId) : [];
  const namespaceItems =
    activeOrgId !== null && activeNamespaceId !== null
      ? namespaceNavItems(activeOrgId, activeNamespaceId)
      : [];

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

        <nav className="flex flex-1 flex-col gap-4 overflow-y-auto p-3" aria-label="Primary">
          {activeOrgId !== null ? (
            <section aria-label={t('nav.world')}>
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {t('nav.world')}
              </p>
              <div className="flex flex-col gap-1">
                {worldItems.map((item) => (
                  <NavLink
                    key={item.labelKey}
                    to={item.to}
                    className={() =>
                      cn(
                        DESKTOP_LINK_CLASS,
                        navActive(item, location.pathname)
                          ? 'bg-blue-600 text-white'
                          : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                      )
                    }
                  >
                    <item.Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{t(item.labelKey)}</span>
                  </NavLink>
                ))}
              </div>
            </section>
          ) : null}

          {activeOrgId !== null && activeNamespaceId !== null ? (
            <section aria-label={t('nav.currentNamespace')}>
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {t('nav.currentNamespace')}
              </p>
              <div className="mb-2 px-1">
                <NamespaceSwitcher orgId={activeOrgId} />
              </div>
              <div className="flex flex-col gap-1">
                {namespaceItems.map((item) => (
                  <NavLink
                    key={item.labelKey}
                    to={item.to}
                    className={() =>
                      cn(
                        DESKTOP_LINK_CLASS,
                        navActive(item, location.pathname)
                          ? 'bg-blue-600 text-white'
                          : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                      )
                    }
                  >
                    <item.Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{t(item.labelKey)}</span>
                  </NavLink>
                ))}
              </div>
            </section>
          ) : null}

          <section aria-label={t('nav.account')}>
            <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              {t('nav.account')}
            </p>
            <div className="flex flex-col gap-1">
              <NavLink
                to="/account"
                className={() =>
                  cn(
                    DESKTOP_LINK_CLASS,
                    navActive(
                      { to: '/account', labelKey: 'nav.account', Icon: User },
                      location.pathname,
                    )
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                  )
                }
              >
                <User className="size-4 shrink-0" aria-hidden="true" />
                <span className="truncate">{t('nav.account')}</span>
              </NavLink>
            </div>
          </section>
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="mb-3 flex items-center justify-between gap-2 px-1">
            <LanguageSwitcher variant="sidebar" placement="up" />
            <span className="font-mono text-[11px] text-slate-500">v{APP_VERSION}</span>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:min-h-0">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="hidden min-w-0 sm:block">
            <p className="truncate text-sm font-semibold text-slate-900">{t('common.appName')}</p>
            <p className="truncate text-xs text-slate-500">{t('common.controlStudio')}</p>
          </div>

          {activeOrgId !== null ? (
            <div className="flex min-w-0 items-center gap-2">
              <OrgSwitcher variant="header" />
              <StatusBar />
            </div>
          ) : null}

          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Link
              to="/account"
              className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50"
            >
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
                <User className="size-4" aria-hidden="true" />
              </span>
              <div className="hidden min-w-0 md:block">
                <p className="max-w-40 truncate text-sm font-medium text-slate-800">
                  {user?.nickname?.trim() ||
                    user?.username ||
                    user?.user_id ||
                    t('common.authenticatedUser')}
                </p>
                <p className="text-xs text-slate-500">{t(identityLabelKey)}</p>
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
          aria-label="Primary mobile"
        >
          {worldItems.map((item) => (
            <NavLink
              key={item.labelKey}
              to={item.to}
              className={() =>
                cn(
                  'shrink-0 rounded-t-lg border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                  navActive(item, location.pathname)
                    ? 'border-blue-600 bg-blue-50 text-blue-700'
                    : 'border-transparent text-slate-500 hover:bg-slate-50',
                )
              }
            >
              {t(item.labelKey)}
            </NavLink>
          ))}
          <NavLink
            to="/account"
            className={() =>
              cn(
                'shrink-0 rounded-t-lg border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                location.pathname === '/account'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-transparent text-slate-500 hover:bg-slate-50',
              )
            }
          >
            {t('nav.account')}
          </NavLink>
        </nav>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <GlobalModals />
    </div>
  );
}
