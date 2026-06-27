"""UK source adapters (legislation.gov.uk, Parliament APIs, Find Case Law, GOV.UK)."""

# importing each module registers its adapter
from . import legislation  # noqa: F401
from . import si           # noqa: F401
from . import guidance     # noqa: F401
from . import regulator_documents  # noqa: F401
from . import bills        # noqa: F401
from . import hansard      # noqa: F401
from . import caselaw      # noqa: F401
