import os

from dotenv import load_dotenv

from integrations.placement_portals.base import BasePlacementPortalAdapter
from integrations.placement_portals.my_college import MyCollegePortalAdapter

load_dotenv()


ADAPTERS = {
    "my_college": MyCollegePortalAdapter,
}


def get_active_adapter() -> BasePlacementPortalAdapter:
    """
    Selects the active portal plugin.

    Syntax:
        PLACEMENT_PORTAL_ADAPTER=my_college

    Later, other colleges can register their own adapter class in ADAPTERS
    without changing the scraper, database, API, or notification code.
    """
    adapter_name = os.getenv("PLACEMENT_PORTAL_ADAPTER", "my_college")
    adapter_class = ADAPTERS.get(adapter_name)

    if not adapter_class:
        available = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unknown placement adapter '{adapter_name}'. Available: {available}")

    return adapter_class()
