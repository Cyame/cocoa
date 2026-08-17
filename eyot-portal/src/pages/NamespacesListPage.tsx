import { Layers } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router';
import { OrganizationNamespacesPanel } from '@/pages/organization/OrganizationWorldPanels';
import { useSessionStore } from '@/stores/session';

export default function NamespacesListPage() {
  const { t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const user = useSessionStore((state) => state.user);
  const isSuperAdmin = user?.is_super_admin ?? false;
  const identity = user?.identity ?? null;
  const canManageNamespaces =
    isSuperAdmin || identity === 'system' || identity === 'org' || identity === 'namespace';

  return (
    <section
      className="mx-auto w-full max-w-5xl p-6 lg:p-8"
      aria-labelledby="namespaces-list-title"
    >
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Layers className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 id="namespaces-list-title" className="text-2xl font-semibold text-slate-950">
            {t('namespaces.title')}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('namespaces.subtitle')}</p>
        </div>
      </header>

      <OrganizationNamespacesPanel
        canWrite={canManageNamespaces}
        orgId={orgId}
        onOpenNamespace={(ns) => {
          if (orgId !== undefined) {
            navigate(`/orgs/${orgId}/namespaces/${ns.id}`);
          }
        }}
      />
    </section>
  );
}
