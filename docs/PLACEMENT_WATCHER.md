# Placement Watcher Implementation Notes

This feature watches a college TPO portal for new placement drives, extracts
company details, reads attached JD documents, summarizes them, and sends
Telegram notifications.

## New Stack Used

### Playwright

Playwright automates a real browser. We use it because TPO portals usually
need login, clicks, and JavaScript-rendered pages.

Syntax used in `integrations/placement_portals/my_college.py`:

```python
from playwright.sync_api import sync_playwright

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True)
page = browser.new_page(accept_downloads=True)

page.goto(login_url, wait_until="networkidle")
page.fill("input[type='email']", username)
page.fill("input[type='password']", password)
page.click("button[type='submit']")

cards = page.locator(".drive-card").all()
company_name = cards[0].locator(".company-name").first.inner_text()
pdf_url = page.locator("a[href$='.pdf']").first.get_attribute("href")
```

### pypdf

`pypdf` reads text from PDF job-description files.

Syntax used in `integrations/document_reader.py`:

```python
from pypdf import PdfReader

reader = PdfReader(path)
for page in reader.pages:
    text = page.extract_text()
```

### python-docx

`python-docx` reads Word `.docx` job-description files.

Syntax used:

```python
from docx import Document

document = Document(path)
text = "\n".join(p.text for p in document.paragraphs)
```

### httpx

`httpx` downloads JD documents from portal links.

Syntax used:

```python
response = httpx.get(url, timeout=30, follow_redirects=True)
path.write_bytes(response.content)
```

### Existing Groq + LangChain

The JD summarizer uses the same LLM stack already present in the project.

Syntax used in `agents/jd_summarizer.py`:

```python
chain = JD_SUMMARY_PROMPT | llm | StrOutputParser()
summary = chain.invoke({
    "company_name": company_name,
    "role": role,
    "criteria": criteria,
    "job_description": job_description,
})
```

## Current Flow

```text
POST /placements/sync
  -> active portal adapter logs in
  -> adapter fetches company drives
  -> JD PDF/DOCX is downloaded if present
  -> document text is extracted
  -> Groq summarizes the JD
  -> SQLite stores the drive
  -> changes are detected by hash comparison
  -> Telegram notification is sent for new/changed drives
```

## First Adapter

The first adapter is:

```text
integrations/placement_portals/my_college.py
```

It is controlled by `.env` values such as:

```env
PLACEMENT_PORTAL_ADAPTER=my_college
TPO_LOGIN_URL=https://tpo.vierp.in
TPO_HOME_URL=https://tpo.vierp.in/home
TPO_DRIVES_URL=https://tpo.vierp.in/apply_company
TPO_USERNAME=your_username
TPO_PASSWORD=your_password
TPO_DRIVE_CARD_SELECTOR=.drive-card
TPO_COMPANY_NAME_SELECTOR=.company-name
```

After we inspect the real portal page, we will replace placeholder selectors
with the exact selectors from your college portal.

For VIERP, the current navigation flow is:

```text
login at https://tpo.vierp.in
  -> portal home https://tpo.vierp.in/home
  -> sidebar item "Scheduled Companies New"
  -> company cards https://tpo.vierp.in/apply_company
  -> click MORE on a card
  -> details page https://tpo.vierp.in/company-info
```

Because `company-info` appears to depend on which card was clicked, the adapter
should click `MORE` with Playwright instead of directly opening the details URL.
The JD attachment may either download directly or open in a new browser tab, so
the final adapter should handle both Playwright download events and PDF links.

## API Endpoints

```text
POST /placements/sync
GET  /placements
GET  /placements/changes
POST /placements/test-login
```

Use `POST /placements/sync?send_notifications=false` for testing without
sending Telegram messages.
