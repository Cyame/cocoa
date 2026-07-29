import { Bug, Building2, Layers, LogOut, Sparkles, User, Users } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, NavLink } from 'react-router';
import ComposerPanel from '@/components/ComposerPanel';
import GlobalModals from '@/components/GlobalModals';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/session';

type IdeShellProps = {
  readonly workspaceId: string;
  readonly workspaceName: string;
  readonly healthLabel: string;
  readonly modeLabel: string;
  readonly children: ReactNode;
};

export default function IdeShell({
  workspaceId,
  workspaceName,
  healthLabel,
  modeLabel,
  children,
}: IdeShellProps) {
  const { t } = useTranslation();
  const token = useSessionStore((state) => state.token);
  const user = useSessionStore((state) => state.user);
  const clearToken = useSessionStore((state) => state.clearToken);

  if (token === null) {
    return <Navigate to="/login" replace />;
  }

  const sidebarItems = [
    { href: '/namespaces?tab=workspace', Icon: Building2, label: t('ide.sidebar.workspaces') },
    { href: '/namespaces?tab=base-classes', Icon: Sparkles, label: t('ide.sidebar.baseClasses') },
    { href: '/namespaces?tab=contracts', Icon: Users, label: t('ide.sidebar.contracts') },
    { href: '/namespaces?tab=entities', Icon: Layers, label: t('ide.sidebar.entities') },
    {
      href: '/namespaces?tab=capability-market',
      Icon: Sparkles,
      label: t('ide.sidebar.capabilityMarket'),
    },
    { href: '/namespaces?tab=debug', Icon: Bug, label: t('ide.sidebar.debug') },
  ];

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-slate-100 text-slate-950">
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-16 shrink-0 flex-col items-center gap-2 border-r border-slate-800 bg-slate-950 py-3 md:flex">
          {sidebarItems.map(({ href, Icon, label }) => (
            <NavLink
              key={href}
              to={href}
              title={label}
              className={({ isActive }) =>
                cn(
                  'grid size-10 place-items-center rounded-lg transition-colors',
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white',
                )
              }
            >
              <Icon className="size-5" aria-hidden="true" />
              <span className="sr-only">{label}</span>
            </NavLink>
          ))}
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
            <Link
              to="/namespaces?tab=workspace"
              className="text-sm font-medium text-slate-600 hover:text-slate-900"
            >
              {t('ide.backToNamespaces')}
            </Link>
            <LanguageSwitcher />
          </div>

          <div className="flex min-h-0 flex-1">
            <main className="min-w-0 flex-1 overflow-hidden">{children}</main>

            <aside
              className="hidden w-[360px] shrink-0 border-l border-slate-200 bg-white lg:flex lg:flex-col"
              aria-label={t('composer.title')}
            >
              <ComposerPanel workspaceId={workspaceId} compact />
            </aside>
          </div>
        </div>
      </div>

      <footer className="flex h-6 shrink-0 items-center justify-between border-t border-slate-200 bg-slate-900 px-3 text-xs text-slate-300">
        <span className="truncate">
          {workspaceName} · {healthLabel} · {modeLabel}
        </span>
        <span className="flex items-center gap-2 truncate">
          <User className="size-3" aria-hidden="true" />
          {user?.user_id ?? t('common.authenticatedUser')}
          <button
            type="button"
            onClick={clearToken}
            className="ml-2 inline-flex size-5 items-center justify-center rounded hover:bg-slate-800"
            aria-label={t('common.logOut')}
          >
            <LogOut className="size-3" aria-hidden="true" />
          </button>
        </span>
      </footer>

      <GlobalModals />
    </div>
  );
}
