import os
import re
import sys
import asyncio
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from integrations.placement_portals.base import BasePlacementPortalAdapter
from integrations.placement_portals.models import PlacementDrive

load_dotenv()

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class MyCollegePortalAdapter(BasePlacementPortalAdapter):
    """
    First real portal adapter for your college TPO portal.

    New stack used here: Playwright.
    - sync_playwright() starts a browser automation session.
    - browser.new_page() opens a browser tab.
    - page.goto(url) navigates to a page.
    - page.fill(selector, value) types into an input.
    - page.click(selector) clicks a button/link.
    - locator(selector).all() reads repeated elements like company cards.

    The selectors are intentionally read from .env until we inspect the real
    portal HTML. After that, we can harden this adapter with exact selectors.
    """

    portal_name = "my_college"

    def __init__(self, config: dict = None):
        config = config or {}
        self.login_url = config.get("tpo_login_url") or os.getenv("TPO_LOGIN_URL", "https://tpo.vierp.in")
        self.home_url = config.get("tpo_home_url") or os.getenv("TPO_HOME_URL", "https://tpo.vierp.in/home")
        self.drives_url = config.get("tpo_drives_url") or os.getenv("TPO_DRIVES_URL", "https://tpo.vierp.in/apply_company")
        self.username = config.get("tpo_username") or os.getenv("TPO_USERNAME", "")
        self.password = config.get("tpo_password") or os.getenv("TPO_PASSWORD", "")
        self.headless = str(config.get("tpo_headless", os.getenv("TPO_HEADLESS", "true"))).lower() != "false"

        self.username_selector = os.getenv("TPO_USERNAME_SELECTOR", "input[type='email']")
        self.password_selector = os.getenv("TPO_PASSWORD_SELECTOR", "input[type='password']")
        self.submit_selector = os.getenv("TPO_SUBMIT_SELECTOR", "button[type='submit']")
        self.drive_card_selector = os.getenv(
            "TPO_DRIVE_CARD_SELECTOR",
            ".v-card.v-sheet"
        )
        self.company_name_selector = os.getenv("TPO_COMPANY_NAME_SELECTOR", ".company-name")
        self.role_selector = os.getenv("TPO_ROLE_SELECTOR", ".role")
        self.min_package_selector = os.getenv("TPO_MIN_PACKAGE_SELECTOR", ".min-package")
        self.max_package_selector = os.getenv("TPO_MAX_PACKAGE_SELECTOR", ".max-package")
        self.location_selector = os.getenv("TPO_LOCATION_SELECTOR", ".location")
        self.duration_selector = os.getenv("TPO_DURATION_SELECTOR", ".duration")
        self.criteria_selector = os.getenv("TPO_CRITERIA_SELECTOR", ".criteria")
        self.deadline_selector = os.getenv("TPO_DEADLINE_SELECTOR", ".deadline")
        self.detail_link_selector = os.getenv("TPO_DETAIL_LINK_SELECTOR", "a")
        self.jd_document_selector = os.getenv("TPO_JD_DOCUMENT_SELECTOR", "a[href$='.pdf']")
        self.apply_link_selector = os.getenv("TPO_APPLY_LINK_SELECTOR", "a")

        self._playwright = None
        self._browser = None
        self._page = None

    def login(self) -> bool:
        if not all([self.login_url, self.drives_url, self.username, self.password]):
            raise ValueError(
                "TPO_LOGIN_URL, TPO_DRIVES_URL, TPO_USERNAME, and TPO_PASSWORD are required."
            )
        placeholder_values = {
            "your_username",
            "your_email",
            "your_tpo_username_or_email",
            "your_password",
            "your_tpo_password",
        }
        if (
            self.username.strip().lower() in placeholder_values
            or self.password.strip().lower() in placeholder_values
        ):
            raise ValueError(
                "TPO_USERNAME or TPO_PASSWORD still contains an example placeholder."
            )

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page(accept_downloads=True)
        self._page.set_default_timeout(15000)
        self._page.set_default_navigation_timeout(20000)

        self._page.goto(self.login_url, wait_until="domcontentloaded")

        username_input = self._page.get_by_placeholder(
            re.compile("username|email", re.IGNORECASE)
        )
        if username_input.count() == 0:
            username_input = self._page.locator(
                f"{self.username_selector}, input[type='text']"
            )

        password_input = self._page.get_by_placeholder(
            re.compile("password", re.IGNORECASE)
        )
        if password_input.count() == 0:
            password_input = self._page.locator(self.password_selector)

        login_button = self._page.get_by_role(
            "button", name=re.compile(r"^login$", re.IGNORECASE)
        )
        if login_button.count() == 0:
            login_button = self._page.locator(self.submit_selector)

        username_input.first.fill(self.username)
        password_input.first.fill(self.password)
        login_button.first.click()

        try:
            self._page.wait_for_url("**/home", timeout=20000)
        except Exception as exc:
            raise RuntimeError(
                "VIERP did not redirect to /home after submitting credentials. "
                f"Current URL: {self._page.url}"
            ) from exc

        # VIERP is an Angular app, so the sidebar can render after the initial
        # /home navigation. Verify authentication through the protected drives
        # route instead of depending on sidebar render timing.
        self._page.goto(self.drives_url, wait_until="domcontentloaded")
        self._page.wait_for_timeout(2000)

        login_form_visible = (
            self._page.get_by_placeholder(
                re.compile("username|email", re.IGNORECASE)
            ).count() > 0
            and self._page.get_by_placeholder(
                re.compile("password", re.IGNORECASE)
            ).count() > 0
        )
        if "/apply_company" not in self._page.url or login_form_visible:
            raise RuntimeError(
                "VIERP redirected after login, but the protected company page "
                f"was not accessible. Current URL: {self._page.url}"
            )

        return True

    def fetch_drives(self) -> List[PlacementDrive]:
        page = self._require_page()
        if "/apply_company" not in page.url:
            page.goto(self.drives_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        body_text = page.locator("body").inner_text()
        if re.search(r"No Schedule Company Found", body_text, flags=re.IGNORECASE):
            return []

        try:
            page.locator("button", has_text=re.compile("more", re.IGNORECASE)).first.wait_for(
                state="visible",
                timeout=30000,
            )
        except Exception as exc:
            body_text = page.locator("body").inner_text()
            if re.search(
                r"No Schedule Company Found",
                body_text,
                flags=re.IGNORECASE,
            ):
                return []
            raise RuntimeError(
                "VIERP company page opened, but no company card with a MORE "
                "button became visible."
            ) from exc

        drives = []
        more_buttons = page.locator(
            "button", has_text=re.compile("more", re.IGNORECASE)
        )
        card_count = more_buttons.count()
        if card_count == 0:
            raise RuntimeError(
                "VIERP company page did not expose any MORE buttons."
            )

        for index in range(card_count):
            # Re-locate cards after each navigation so Playwright does not use
            # stale DOM handles when returning from /company-info.
            if index > 0 or "/apply_company" not in page.url:
                page.goto(self.drives_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            more_button = page.locator(
                "button", has_text=re.compile("more", re.IGNORECASE)
            ).nth(index)
            card = more_button.locator(
                "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' v-card ')][1]"
            )
            card_text = card.inner_text().strip()
            company_name = self._text(card, self.company_name_selector) or self._company_from_card(card_text)
            if not company_name:
                continue

            detail_url = self._href(card, self.detail_link_selector)
            drive = PlacementDrive(
                portal_name=self.portal_name,
                external_id=detail_url or f"{self.portal_name}:{company_name}:{index}",
                company_name=company_name,
                role=self._text(card, self.role_selector) or self._line_after_company(card_text),
                min_package=self._text(card, self.min_package_selector),
                max_package=self._text(card, self.max_package_selector),
                location=self._text(card, self.location_selector),
                duration=self._text(card, self.duration_selector),
                criteria=self._text(card, self.criteria_selector),
                deadline_date=self._text(card, self.deadline_selector) or self._deadline_from_card(card_text)[0],
                deadline_time=self._deadline_from_card(card_text)[1],
                apply_url=detail_url,
            )

            drive = self._open_and_enrich_from_more(card, drive)

            drives.append(drive)

        return drives

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _enrich_from_details(self, drive: PlacementDrive, detail_url: str) -> PlacementDrive:
        page = self._require_page()
        page.goto(detail_url, wait_until="domcontentloaded")
        return self._extract_detail_page(drive)

    def _open_and_enrich_from_more(self, card, drive: PlacementDrive) -> PlacementDrive:
        page = self._require_page()
        more = card.locator("button", has_text=re.compile("more", re.IGNORECASE))

        more.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        return self._extract_detail_page(drive)

    def _extract_detail_page(self, drive: PlacementDrive) -> PlacementDrive:
        page = self._require_page()
        detail_text = page.locator("body").inner_text()

        drive.role = self._first(drive.role, self._text(page, self.role_selector))
        drive.min_package = self._first(drive.min_package, self._text(page, self.min_package_selector))
        drive.max_package = self._first(drive.max_package, self._text(page, self.max_package_selector))
        drive.min_stipend = self._first(drive.min_stipend, self._label(detail_text, "Min Stipend"))
        drive.max_stipend = self._first(drive.max_stipend, self._label(detail_text, "Max Stipend"))
        drive.location = self._first(drive.location, self._text(page, self.location_selector))
        drive.duration = self._first(drive.duration, self._text(page, self.duration_selector))
        drive.criteria = self._first(drive.criteria, self._text(page, self.criteria_selector))
        drive.deadline_date = self._first(drive.deadline_date, self._text(page, self.deadline_selector))

        drive.company_name = self._first(self._label(detail_text, "Company"), drive.company_name)
        drive.external_id = self._first(self._label(detail_text, "Company Code"), drive.external_id)
        drive.role = self._first(self._label(detail_text, "Offering"), drive.role)
        drive.min_package = self._first(self._label(detail_text, "Min Package"), drive.min_package)
        drive.max_package = self._first(self._label(detail_text, "Max Package"), drive.max_package)
        drive.location = self._first(self._label(detail_text, "Job Locations"), drive.location)
        drive.duration = self._first(self._label(detail_text, "Internship Type"), drive.duration)
        drive.criteria = self._first(
            self._combine_criteria(detail_text),
            drive.criteria,
        )
        drive.eligible_branches = self._eligible_branches(detail_text)

        download_link = page.locator(
            "a", has_text=re.compile(r"download", re.IGNORECASE)
        ).first
        drive.document_url = (
            download_link.get_attribute("href")
            if download_link.count() > 0
            else self._href(page, self.jd_document_selector)
        )
        drive.apply_url = page.url
        return drive

    def _require_page(self):
        if not self._page:
            raise RuntimeError("Call login() before fetching drives.")
        return self._page

    @staticmethod
    def _text(scope, selector: str) -> Optional[str]:
        try:
            locator = scope.locator(selector).first
            if locator.count() == 0:
                return None
            text = locator.inner_text().strip()
            return text or None
        except Exception:
            return None

    @staticmethod
    def _href(scope, selector: str) -> Optional[str]:
        try:
            locator = scope.locator(selector).first
            if locator.count() == 0:
                return None
            href = locator.get_attribute("href")
            return href or None
        except Exception:
            return None

    @staticmethod
    def _first(*values):
        for value in values:
            if value:
                return value
        return None

    @staticmethod
    def _company_from_card(card_text: str) -> Optional[str]:
        lines = [line.strip() for line in card_text.splitlines() if line.strip()]
        ignored = {"APPLY", "MORE", "Regular"}
        for line in lines:
            if line not in ignored and not re.search(r"\d{1,2}-[A-Za-z]{3}-\d{4}", line):
                return line
        return None

    @staticmethod
    def _line_after_company(card_text: str) -> Optional[str]:
        lines = [line.strip() for line in card_text.splitlines() if line.strip()]
        if len(lines) >= 2:
            return lines[1]
        return None

    @staticmethod
    def _deadline_from_card(card_text: str) -> tuple:
        match = re.search(
            r"(\d{1,2}-[A-Za-z]{3}-\d{4})(?:\s+(\d{1,2}:\d{2}))?",
            card_text,
        )
        if not match:
            return None, None
        return match.group(1), match.group(2)

    @staticmethod
    def _label(page_text: str, label: str) -> Optional[str]:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        exact_line = re.compile(
            rf"^{re.escape(label)}\s*:\s*(.+?)\s*$",
            flags=re.IGNORECASE,
        )
        for line in lines:
            match = exact_line.match(line)
            if match:
                value = match.group(1).strip(" :")
                if value:
                    return value

        for index, line in enumerate(lines):
            if re.fullmatch(re.escape(label), line, flags=re.IGNORECASE):
                for candidate in lines[index + 1:index + 4]:
                    value = candidate.strip(" :")
                    if value and not re.fullmatch(r":", value):
                        return value

        labels = [
            "Company", "Company Code", "Company Type", "Schedule Date",
            "Industry Type", "Min Package", "Max Package", "Job Locations",
            "Min Stipend", "Max Stipend", "Internship Type", "Dead Backlog",
            "Live Backlog", "Specific Criteria", "Placed student",
            "Intern student", "Offering", "Year Down", "Package Description",
            "Stipend Description", "Bond Description", "Semester",
            "Dream Company Package", "Placement Mode", "Incharge Faculty",
            "Collaborators", "Is Drive Completed?", "Remark"
        ]
        boundary = "|".join(re.escape(item) for item in labels if item != label)
        pattern = rf"{re.escape(label)}\s*:\s*(.*?)(?=\s+(?:{boundary})\s*:|\n(?:{boundary})\b|$)"
        match = re.search(pattern, page_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        value = re.sub(r"\s+", " ", match.group(1)).strip(" :")
        return value or None

    def _combine_criteria(self, page_text: str) -> Optional[str]:
        parts = []
        for label in [
            "Specific Criteria",
            "Dead Backlog",
            "Live Backlog",
            "Placed student",
            "Intern student",
            "Year Down",
            "Semester",
        ]:
            value = self._label(page_text, label)
            if value:
                parts.append(f"{label}: {value}")
        return "; ".join(parts) if parts else None

    @staticmethod
    def _eligible_branches(page_text: str) -> Optional[str]:
        if "Eligible Branches" not in page_text:
            return None
        section = page_text.split("Eligible Branches", 1)[1]
        section = re.split(r"\n\s*\n|Rows per page|Company Attachments", section, maxsplit=1)[0]
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        useful = [
            line for line in lines
            if line not in {"Organization", "Program", "Year"}
        ]
        return "; ".join(useful[:30]) if useful else None

    def _capture_download_if_possible(self, drive: PlacementDrive):
        page = self._require_page()
        download_link = page.get_by_text(re.compile(r"^Download$", re.IGNORECASE))
        if download_link.count() == 0:
            return

        download_dir = Path("storage") / "placement_documents"
        download_dir.mkdir(parents=True, exist_ok=True)

        try:
            with page.expect_download(timeout=5000) as download_info:
                download_link.first.click()
            download = download_info.value
            filename = download.suggested_filename or f"{drive.company_name}_jd.pdf"
            path = download_dir / filename
            download.save_as(str(path))
            drive.local_document = str(path)
            drive.document_url = self._first(drive.document_url, page.url)
            return
        except Exception:
            pass

        try:
            with page.context.expect_page(timeout=5000) as page_info:
                download_link.first.click()
            new_page = page_info.value
            new_page.wait_for_load_state("networkidle")
            drive.document_url = self._first(drive.document_url, new_page.url)
            new_page.close()
        except Exception:
            href = self._href(page, "a")
            drive.document_url = self._first(drive.document_url, href)
