"""Cloud storage integration — Google Drive and OneDrive.

Supports:
1. Google Drive — watch folders, auto-import new documents
2. OneDrive / SharePoint — watch folders via Microsoft Graph API

Both use OAuth2 for authentication and webhook subscriptions for change detection.
"""

from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class GoogleDriveService:
    """Google Drive integration for document import."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_URL = "https://www.googleapis.com/drive/v3"
    SCOPES = "https://www.googleapis.com/auth/drive.readonly"

    def __init__(self):
        self.settings = get_settings()

    def get_auth_url(self, redirect_uri: str, state: str = "") -> str:
        params = {
            "client_id": self.settings.gdrive_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": self.settings.gdrive_client_id,
                "client_secret": self.settings.gdrive_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            data = resp.json()
            if "error" in data:
                raise ValueError(f"Google OAuth error: {data.get('error_description', data['error'])}")
            return {"access_token": data["access_token"], "refresh_token": data.get("refresh_token")}

    async def refresh_access_token(self, refresh_token: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_id": self.settings.gdrive_client_id,
                "client_secret": self.settings.gdrive_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            return resp.json()["access_token"]

    async def list_folder(self, access_token: str, folder_id: str = "root") -> list[dict]:
        """List files in a Google Drive folder."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.API_URL}/files",
                params={
                    "q": f"'{folder_id}' in parents and trashed = false",
                    "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)",
                    "orderBy": "modifiedTime desc",
                    "pageSize": "100",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()
            return [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "mime_type": f["mimeType"],
                    "size": int(f.get("size", 0)),
                    "modified": f.get("modifiedTime"),
                    "url": f.get("webViewLink"),
                }
                for f in data.get("files", [])
            ]

    async def download_file(self, access_token: str, file_id: str) -> bytes:
        """Download a file's content from Google Drive."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.API_URL}/files/{file_id}",
                params={"alt": "media"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=60.0,
            )
            if resp.status_code != 200:
                raise ValueError(f"Failed to download file: {resp.status_code}")
            return resp.content

    async def list_folders(self, access_token: str) -> list[dict]:
        """List folders the user has access to (for folder picker)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.API_URL}/files",
                params={
                    "q": "mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                    "fields": "files(id,name)",
                    "orderBy": "name",
                    "pageSize": "100",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return [{"id": f["id"], "name": f["name"]} for f in resp.json().get("files", [])]


class OneDriveService:
    """OneDrive / SharePoint integration via Microsoft Graph API."""

    AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    SCOPES = "Files.Read.All offline_access"

    def __init__(self):
        self.settings = get_settings()
        # OneDrive reuses gdrive client credentials for now
        # In production, these would be separate Azure AD app credentials
        self.client_id = self.settings.gdrive_client_id
        self.client_secret = self.settings.gdrive_client_secret

    def get_auth_url(self, redirect_uri: str, state: str = "") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": self.SCOPES,
            })
            data = resp.json()
            if "error" in data:
                raise ValueError(f"Microsoft OAuth error: {data.get('error_description', data['error'])}")
            return {"access_token": data["access_token"], "refresh_token": data.get("refresh_token")}

    async def list_folder(self, access_token: str, folder_path: str = "/me/drive/root/children") -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.GRAPH_URL}{folder_path}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()
            return [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "mime_type": item.get("file", {}).get("mimeType", "folder"),
                    "size": item.get("size", 0),
                    "modified": item.get("lastModifiedDateTime"),
                    "url": item.get("webUrl"),
                }
                for item in data.get("value", [])
            ]

    async def download_file(self, access_token: str, item_id: str) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.GRAPH_URL}/me/drive/items/{item_id}/content",
                headers={"Authorization": f"Bearer {access_token}"},
                follow_redirects=True,
                timeout=60.0,
            )
            return resp.content
