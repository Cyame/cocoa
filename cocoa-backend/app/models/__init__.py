"""SQLAlchemy ORM models. Importing each module here registers its tables
with :data:`app.core.db.Base.metadata`, which is required for Alembic
autogenerate to detect schema drift.

> **15d-rename (2026-07-29)**: `app.models.blackboard` was renamed to
> `app.models.central_hub` and class names updated to `CentralHub` /
> `FornixFile` / `Vault` / `VaultEntry`. No back-compat aliases — no prod data.
"""

import app.models.ai_gene  # noqa: E402, F401
import app.models.base_class  # noqa: E402, F401
import app.models.capability_market  # noqa: E402, F401
import app.models.central_hub  # noqa: E402, F401
import app.models.corridor_node  # noqa: E402, F401
import app.models.deploy_record  # noqa: E402, F401
import app.models.employee  # noqa: E402, F401
import app.models.event  # noqa: E402, F401
import app.models.instance  # noqa: E402, F401
import app.models.instance_provider_config  # noqa: E402, F401
import app.models.loop_state  # noqa: E402, F401
import app.models.memory  # noqa: E402, F401
import app.models.office  # noqa: E402, F401
import app.models.user  # noqa: E402, F401

# Public re-exports (15d+ canonical names)
from app.models.ai_gene import (  # noqa: E402, F401
    AiGene,
    AiGeneKind,
)
from app.models.base_class import BaseClass  # noqa: E402, F401
from app.models.capability_market import (  # noqa: E402, F401
    CapabilityCreatedVia,
    CapabilityMarketEntry,
    CapabilityType,
)
from app.models.central_hub import (  # noqa: E402, F401
    BrainstemSchedule,
    CentralHub,
    CerebellumAgent,
    CerebellumAgentType,
    FornixFile,
    FrontalLobeKanban,
    FrontalLobeKanbanStatus,
    Vault,
    VaultEntry,
    VaultEntrySourceType,
)
