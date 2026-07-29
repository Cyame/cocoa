import { Bug, Building2, Layers, LogOut, Settings, Sparkles, User, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Navigate, NavLink, Outlet, useSearchParams } from 'react-router';
import GlobalModals from '@/components/GlobalModals';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/session';

const TAB_IDS = [
  'workspace',
  'base-classes',
  'contracts',
  'entities',
  'capability-market',
  'debug',
] as const;

export type NamespaceTabId = (typeof TAB_IDS)[number];

const DESKTOP_LINK_CLASS =
  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500';

export default function AppShell() {
  const { t } = useTranslation();
  const token = useSessionStore((state) => state.token);
  const user = useSessionStore((state) => state.user);
  const clearToken = useSessionStore((state) => state.clearToken);
  const [searchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') ?? 'workspace') as NamespaceTabId;

  if (token === null) {
    return <Navigate to="/login" replace />;
  }

  const tabItems = [
    { id: 'workspace' as const, label: t('namespaces.tabs.workspace'), Icon: Building2 },
    { id: 'base-classes' as const, label: t('namespaces.tabs.baseClasses'), Icon: Sparkles },
    { id: 'contracts' as const, label: t('namespaces.tabs.contracts'), Icon: Users },
    { id: 'entities' as const, label: t('namespaces.tabs.entities'), Icon: Layers },
    {
      id: 'capability-market' as const,
      label: t('namespaces.tabs.capabilityMarket'),
      Icon: Settings,
    },
    { id: 'debug' as const, label: t('namespaces.tabs.debug'), Icon: Bug },
  ];

  return (
    <div className="flex min-h-dvh bg-slate-100 text-slate-950 md:h-dvh md:overflow-hidden">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100 md:flex">
        <div className="flex h-16 items-center gap-3 border-b border-slate-800 px-5">
          <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white">
            <Building2 className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight">{t('common.appName')}</p>
            <p className="truncate text-xs text-slate-400">{t('common.controlStudio')}</p>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Namespace navigation">
          {tabItems.map(({ id, label, Icon }) => (
            <NavLink
              key={id}
              to={`/namespaces?tab=${id}`}
              className={() =>
                cn(
                  DESKTOP_LINK_CLASS,
                  activeTab === id
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                )
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-3">
          <NavLink
            to="/organization"
            className={({ isActive }) =>
              cn(
                DESKTOP_LINK_CLASS,
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white',
              )
            }
          >
            <Settings className="size-4 shrink-0" aria-hidden="true" />
            <span className="truncate">{t('nav.organization')}</span>
          </NavLink>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:min-h-0">
        <div className="flex h-10 shrink-0 items-center justify-end gap-3 border-b border-slate-200 bg-slate-50 px-4 sm:px-6">
          <LanguageSwitcher />
        </div>

        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{t('namespaces.title')}</p>
            <p className="truncate text-xs text-slate-500">{t('namespaces.subtitle')}</p>
          </div>

          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
                <User className="size-4" aria-hidden="true" />
              </span>
              <div className="hidden min-w-0 sm:block">
                <p className="max-w-48 truncate text-sm font-medium text-slate-800">
                  {user?.user_id ?? t('common.authenticatedUser')}
                </p>
                <p className="text-xs text-slate-500">
                  {user?.is_super_admin === true ? t('common.superAdmin') : t('common.operator')}
                </p>
              </div>
            </div>
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
          aria-label="Namespace tabs"
        >
          {tabItems.map(({ id, label }) => (
            <NavLink
              key={id}
              to={`/namespaces?tab=${id}`}
              className={() =>
                cn(
                  'shrink-0 rounded-t-lg border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                  activeTab === id
                    ? 'border-blue-600 bg-blue-50 text-blue-700'
                    : 'border-transparent text-slate-500 hover:bg-slate-50',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <GlobalModals />
    </div>
  );
}
