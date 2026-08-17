import { Building2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DeepSeaGenesPanel, HumanGenesPanel } from '@/components/namespaces/CatalogGeneCrudPanels';

export default function GenesPage() {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState<'deep-sea' | 'human'>('deep-sea');

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="genes-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
          <Building2 className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 id="genes-title" className="text-2xl font-semibold text-slate-950">
            {t('nav.genes')}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('namespaces.genesDetail')}</p>
        </div>
      </header>

      <div className="space-y-4">
        <div
          role="tablist"
          aria-label={t('nav.genes')}
          className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1"
          data-testid="genes-subtabs"
        >
          {(
            [
              { id: 'deep-sea' as const, label: t('namespaces.genesSubDeepSea') },
              { id: 'human' as const, label: t('namespaces.genesSubHuman') },
            ] as const
          ).map((tab) => {
            const active = subTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`genes-subtab-${tab.id}`}
                onClick={() => setSubTab(tab.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  active
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:bg-white hover:text-slate-900'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {subTab === 'deep-sea' ? <DeepSeaGenesPanel t={t} /> : <HumanGenesPanel t={t} />}
      </div>
    </section>
  );
}
