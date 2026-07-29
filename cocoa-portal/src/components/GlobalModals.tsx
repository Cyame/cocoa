import EntityDetailModal from '@/components/EntityDetailModal';
import FirstRunOnboardingModal from '@/pages/FirstRunOnboardingModal';
import { useEntityModalStore } from '@/stores/entityModalStore';
import { useOnboardingModalStore } from '@/stores/onboardingModalStore';

type GlobalModalsProps = {
  readonly onOnboardingComplete?: () => void;
};

export default function GlobalModals({ onOnboardingComplete }: GlobalModalsProps) {
  const entityId = useEntityModalStore((state) => state.entityId);
  const closeEntityModal = useEntityModalStore((state) => state.close);
  const onboardingOpen = useOnboardingModalStore((state) => state.isOpen);
  const closeOnboarding = useOnboardingModalStore((state) => state.close);

  return (
    <>
      {entityId !== null ? <EntityDetailModal onClose={closeEntityModal} /> : null}
      {onboardingOpen ? (
        <FirstRunOnboardingModal
          onClose={(reason) => {
            closeOnboarding();
            if (reason === 'completed') onOnboardingComplete?.();
          }}
        />
      ) : null}
    </>
  );
}
