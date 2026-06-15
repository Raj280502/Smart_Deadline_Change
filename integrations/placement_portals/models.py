from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class PlacementDrive:
    """
    Normalized placement-drive shape used by every portal adapter.

    Any college portal can have different HTML, labels, or navigation, but it
    must return this common object so the rest of the app stays unchanged.
    """

    portal_name: str
    company_name: str
    external_id: Optional[str] = None
    role: Optional[str] = None
    min_package: Optional[str] = None
    max_package: Optional[str] = None
    min_stipend: Optional[str] = None
    max_stipend: Optional[str] = None
    location: Optional[str] = None
    duration: Optional[str] = None
    criteria: Optional[str] = None
    eligible_branches: Optional[str] = None
    deadline_date: Optional[str] = None
    deadline_time: Optional[str] = None
    job_description: Optional[str] = None
    jd_summary: Optional[str] = None
    document_url: Optional[str] = None
    local_document: Optional[str] = None
    apply_url: Optional[str] = None
    status: str = "open"

    def to_dict(self) -> dict:
        return asdict(self)
