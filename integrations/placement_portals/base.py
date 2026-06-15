from abc import ABC, abstractmethod
from typing import List

from integrations.placement_portals.models import PlacementDrive


class BasePlacementPortalAdapter(ABC):
    """
    Plugin contract for placement portals.

    Syntax idea:
        adapter = MyCollegePortalAdapter()
        adapter.login()
        drives = adapter.fetch_drives()

    Playwright gives each adapter a browser page. The adapter uses CSS
    selectors such as "#email" or ".company-card" to type, click, and read
    text from the actual portal.
    """

    portal_name = "base"

    @abstractmethod
    def login(self) -> bool:
        """Open the portal login page and authenticate."""

    @abstractmethod
    def fetch_drives(self) -> List[PlacementDrive]:
        """Return normalized placement drives from the portal."""

    def close(self):
        """Release browser/session resources if the adapter owns any."""
