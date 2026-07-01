import json
from urllib.parse import urljoin

from agents.jd_summarizer import summarize_jd
from agents.placement_notification import (
    notify_changed_placement_drive,
    notify_new_placement_drive,
    notify_no_placement_drives,
)
from integrations.document_reader import (
    download_document,
    extract_text_from_document,
)
from integrations.placement_portals.registry import get_active_adapter
from storage.placement_repository import (
    finish_scrape_run,
    start_scrape_run,
    upsert_placement_drive,
)


def sync_placement_drives(
    send_notifications: bool = True,
    credentials: dict = None,
    user_id: int = 1,
) -> dict:
    """
    Main placement watcher flow.

    Flow:
        adapter.login()
        adapter.fetch_drives()
        read JD document
        summarize JD
        upsert into DB
        notify Telegram
    """
    credentials = credentials or {}
    adapter = get_active_adapter(config=credentials)
    run_id = start_scrape_run(adapter.portal_name, user_id=user_id)
    new_count = 0
    changed_count = 0
    no_drive_notification_sent = False
    results = []

    try:
        adapter.login()
        drives = adapter.fetch_drives()

        if send_notifications and not drives:
            no_drive_notification_sent = notify_no_placement_drives(
                portal_name=adapter.portal_name,
                bot_token=credentials.get("telegram_bot_token"),
                chat_id=credentials.get("telegram_chat_id"),
            )

        for drive_obj in drives:
            drive = drive_obj.to_dict()
            drive = enrich_drive_with_document_text(drive, getattr(adapter, "drives_url", ""))

            summary = summarize_jd(
                company_name=drive.get("company_name"),
                role=drive.get("role"),
                criteria=drive.get("criteria"),
                job_description=drive.get("job_description"),
                api_key=credentials.get("groq_api_key"),
            )
            drive["jd_summary"] = json.dumps(summary, ensure_ascii=True)

            saved_drive, changes, is_new = upsert_placement_drive(drive, user_id=user_id)

            if is_new:
                new_count += 1
                if send_notifications:
                    notify_new_placement_drive(
                        saved_drive,
                        bot_token=credentials.get("telegram_bot_token"),
                        chat_id=credentials.get("telegram_chat_id"),
                    )
            elif changes:
                changed_count += 1
                if send_notifications:
                    notify_changed_placement_drive(
                        saved_drive,
                        changes,
                        bot_token=credentials.get("telegram_bot_token"),
                        chat_id=credentials.get("telegram_chat_id"),
                    )

            results.append({
                "drive": saved_drive,
                "is_new": is_new,
                "changes": changes,
            })

        finish_scrape_run(run_id, "success", new_count, changed_count)
        return {
            "status": "success",
            "portal_name": adapter.portal_name,
            "total_seen": len(drives),
            "new_drives": new_count,
            "changed_drives": changed_count,
            "no_drive_notification_sent": no_drive_notification_sent,
            "results": results,
        }
    except Exception as exc:
        finish_scrape_run(run_id, "failed", new_count, changed_count, str(exc))
        return {
            "status": "failed",
            "portal_name": adapter.portal_name,
            "error": str(exc),
            "new_drives": new_count,
            "changed_drives": changed_count,
        }
    finally:
        adapter.close()


def enrich_drive_with_document_text(drive: dict, base_url: str = "") -> dict:
    """
    If the portal exposes a JD PDF/DOCX link, download and extract its text.
    If no document exists, we keep any visible job_description text from page.
    """
    local_document = drive.get("local_document")
    if local_document:
        document_text = extract_text_from_document(local_document)
        if document_text:
            visible_text = drive.get("job_description") or ""
            drive["job_description"] = "\n\n".join(
                part for part in [visible_text, document_text] if part
            )
        return drive

    document_url = drive.get("document_url")
    if not document_url:
        return drive

    absolute_url = urljoin(base_url, document_url)
    drive["document_url"] = absolute_url

    local_path = download_document(
        absolute_url,
        filename_hint=f"{drive.get('company_name', 'company')}_jd",
    )
    drive["local_document"] = local_path

    document_text = extract_text_from_document(local_path)
    if document_text:
        visible_text = drive.get("job_description") or ""
        drive["job_description"] = "\n\n".join(
            part for part in [visible_text, document_text] if part
        )

    return drive
