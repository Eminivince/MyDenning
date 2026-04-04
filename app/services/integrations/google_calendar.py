"""Google Calendar bidirectional sync.

Flow:
1. User authenticates via OAuth2 (GET /integrations/google/auth -> redirect)
2. Callback stores refresh_token per user
3. Sync pushes MyDenning events to Google Calendar
4. Sync pulls Google Calendar events into MyDenning
5. Celery task runs periodic sync

Requires: google_client_id and google_client_secret in settings.
"""

import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar"


class GoogleCalendarService:
    def __init__(self):
        self.settings = get_settings()

    def get_auth_url(self, redirect_uri: str, state: str = "") -> str:
        """Generate the OAuth2 consent URL for the user to authorize."""
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access + refresh tokens."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            data = resp.json()
            if "error" in data:
                raise ValueError(f"Google OAuth error: {data['error_description']}")
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 3600),
            }

    async def refresh_access_token(self, refresh_token: str) -> str:
        """Get a new access token using the refresh token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            data = resp.json()
            return data["access_token"]

    async def push_event(self, access_token: str, event: dict) -> dict:
        """Push a MyDenning calendar event to Google Calendar.

        event should have: title, start_time, end_time, description, location
        """
        google_event = {
            "summary": event.get("title", ""),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start": {"dateTime": event["start_time"], "timeZone": "UTC"},
            "end": {"dateTime": event.get("end_time", event["start_time"]), "timeZone": "UTC"},
        }
        if event.get("attendee_emails"):
            google_event["attendees"] = [{"email": e} for e in event["attendee_emails"]]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GOOGLE_CALENDAR_API}/calendars/primary/events",
                json=google_event,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()
            if resp.status_code not in (200, 201):
                logger.error("google_push_failed", error=data)
                raise ValueError(f"Google Calendar error: {data.get('error', {}).get('message', 'Unknown')}")
            logger.info("google_event_pushed", google_id=data.get("id"))
            return {"google_event_id": data["id"], "html_link": data.get("htmlLink")}

    async def pull_events(self, access_token: str, time_min: str, time_max: str) -> list[dict]:
        """Pull events from Google Calendar within a time range."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/primary/events",
                params={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": "100",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()
            events = []
            for item in data.get("items", []):
                start = item.get("start", {})
                end = item.get("end", {})
                events.append({
                    "google_id": item.get("id"),
                    "title": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "location": item.get("location", ""),
                    "start_time": start.get("dateTime", start.get("date", "")),
                    "end_time": end.get("dateTime", end.get("date", "")),
                    "attendees": [a.get("email") for a in item.get("attendees", [])],
                    "html_link": item.get("htmlLink"),
                })
            return events

    async def delete_event(self, access_token: str, google_event_id: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{GOOGLE_CALENDAR_API}/calendars/primary/events/{google_event_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return resp.status_code in (200, 204)
