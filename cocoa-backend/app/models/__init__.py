"""SQLAlchemy ORM models. Importing each module here registers its tables
with :data:`app.core.db.Base.metadata`, which is required for Alembic
autogenerate to detect schema drift.
"""

import app.models.blackboard  # noqa: E402, F401
import app.models.employee  # noqa: E402, F401
import app.models.event  # noqa: E402, F401
import app.models.instance  # noqa: E402, F401
import app.models.loop_state  # noqa: E402, F401
import app.models.memory  # noqa: E402, F401
import app.models.office  # noqa: E402, F401
import app.models.user  # noqa: E402, F401
