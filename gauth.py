"""Auth helpers — Google Sheets (service account) + Meta Ads API.

Local: cai automaticamente nos .env das skills do Patrick.
CI:    usa env vars (GOOGLE_SHEETS_CREDENTIALS_PATH, META_ADS_TOKEN, META_APP_ID).
"""
import os
import sys

_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# fallbacks locais (nao usados no CI)
_LOCAL_SHEETS_ENV = os.path.expanduser("~/.claude/skills/google-sheets/.env")
_LOCAL_META_ENV = os.path.expanduser("~/.claude/skills/meta-ads-instituto-id/.env")


def _read_env_file(path, key):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    cred_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
    if not cred_path:
        cred_path = _read_env_file(_LOCAL_SHEETS_ENV, "GOOGLE_SHEETS_CREDENTIALS_PATH")
    if not cred_path or not os.path.exists(cred_path):
        sys.exit(f"[gauth] credenciais Sheets nao encontradas (GOOGLE_SHEETS_CREDENTIALS_PATH={cred_path})")
    creds = Credentials.from_service_account_file(cred_path, scopes=_SHEETS_SCOPES)
    return gspread.authorize(creds)


def init_meta():
    from facebook_business.api import FacebookAdsApi

    token = os.environ.get("META_ADS_TOKEN") or _read_env_file(_LOCAL_META_ENV, "META_ADS_TOKEN")
    app_id = os.environ.get("META_APP_ID") or _read_env_file(_LOCAL_META_ENV, "META_APP_ID")
    if not token:
        sys.exit("[gauth] META_ADS_TOKEN nao configurado")
    FacebookAdsApi.init(app_id=app_id, access_token=token, api_version="v21.0")
    return token, app_id
