"""SQLAlchemy ORM model registry (PRD-v2)."""

import app.models.ai_gene  # noqa: E402, F401
import app.models.base_class  # noqa: E402, F401
import app.models.base_class_provider_default  # noqa: E402, F401
import app.models.capability_market  # noqa: E402, F401
import app.models.central_hub  # noqa: E402, F401
import app.models.composer_message  # noqa: E402, F401
import app.models.deploy_record  # noqa: E402, F401
import app.models.entity  # noqa: E402, F401
import app.models.event  # noqa: E402, F401
import app.models.instance  # noqa: E402, F401
import app.models.instance_provider_config  # noqa: E402, F401
import app.models.junctions  # noqa: E402, F401
import app.models.loop_state  # noqa: E402, F401
import app.models.memory  # noqa: E402, F401
import app.models.namespace_contract  # noqa: E402, F401
import app.models.organization  # noqa: E402, F401
import app.models.organization_contract  # noqa: E402, F401
import app.models.organization_provider  # noqa: E402, F401
import app.models.user  # noqa: E402, F401
import app.models.user_gene  # noqa: E402, F401
import app.models.workspace  # noqa: E402, F401

from app.models.ai_gene import AiGene, BaseClassAiGene  # noqa: E402, F401
from app.models.base_class import BaseClass  # noqa: E402, F401
from app.models.base_class_provider_default import (  # noqa: E402, F401
    BaseClassProviderDefault,
)
from app.models.capability_market import (  # noqa: E402, F401
    CapabilityCreatedVia,
    CapabilityMarketEntry,
    CapabilityType,
)
from app.models.composer_message import ComposerMessage  # noqa: E402, F401
from app.models.central_hub import (  # noqa: E402, F401
    BrainstemSchedule,
    CentralHub,
    CerebellumAgent,
    FornixFile,
    FrontalLobeKanban,
    FrontalLobeKanbanStatus,
    Vault,
    VaultEntry,
    VaultEntrySourceType,
)
from app.models.entity import Entity, EntityRank  # noqa: E402, F401
from app.models.junctions import (  # noqa: E402, F401
    BaseClassCapability,
    EntityAiGene,
    EntityCapability,
)
from app.models.memory import Memory, Memory, MemoryKind  # noqa: E402, F401
from app.models.namespace_contract import (  # noqa: E402, F401
    NamespaceContract,
    NamespaceContractGene,
)
from app.models.organization import Namespace, Organization  # noqa: E402, F401
from app.models.organization_contract import (  # noqa: E402, F401
    OrganizationContract,
    OrganizationContractGene,
)
from app.models.organization_provider import OrganizationProvider  # noqa: E402, F401
from app.models.user_gene import (  # noqa: E402, F401
    UserGene,
    UserGeneEffectScope,
    UserGeneKind,
    UserUserGene,
)
from app.models.workspace import (  # noqa: E402, F401
    Membership,
    Passage,
    Workspace,
)
