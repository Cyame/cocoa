import { Building2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { CapabilityMarketTab } from '@/components/namespaces/CatalogGeneCrudPanels';

export default function CapabilitiesPage() {
  const { t } = useTranslation();

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="capabilities-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Building2 className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 id="capabilities-title" className="text-2xl font-semibold text-slate-950">
            {t('nav.capabilities')}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            {t('namespaces.capabilityMarketDetail')}
          </p>
        </div>
      </header>

      <CapabilityMarketTab t={t} />
    </section>
  );
}
