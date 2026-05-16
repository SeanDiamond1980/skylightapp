import json
import os
import secrets
import urllib.parse
from datetime import datetime, timezone

import requests as http
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from database import get_setting, set_setting

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

# ── OAuth (raw HTTP — avoids PKCE issues with the Flow library) ───────────────

def get_auth_url() -> tuple:
    state = secrets.token_urlsafe(16)
    params = {
        'client_id': os.environ['GOOGLE_CLIENT_ID'],
        'redirect_uri': os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback'),
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    }
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return url, state

def exchange_code_for_tokens(code: str, state: str = None) -> dict:
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback')

    # Exchange code for tokens
    resp = http.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': os.environ['GOOGLE_CLIENT_ID'],
        'client_secret': os.environ['GOOGLE_CLIENT_SECRET'],
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    })
    tokens = resp.json()
    if 'error' in tokens:
        raise ValueError(tokens.get('error_description', tokens['error']))

    access_token = tokens['access_token']

    # Get the user's email
    user_resp = http.get(
        'https://www.googleapis.com/oauth2/v2/userinfo',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    email = user_resp.json().get('email', 'unknown')

    token_data = {
        'email': email,
        'token': access_token,
        'refresh_token': tokens.get('refresh_token'),
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': os.environ['GOOGLE_CLIENT_ID'],
        'client_secret': os.environ['GOOGLE_CLIENT_SECRET'],
        'scopes': SCOPES,
        'calendar_id': 'primary',
    }

    accounts = _get_accounts()
    accounts = [a for a in accounts if a.get('email') != email]
    accounts.append(token_data)
    _save_accounts(accounts)
    set_setting('google_tokens', json.dumps(token_data))

    return token_data

# ── Account management ────────────────────────────────────────────────────────

def _get_accounts() -> list:
    raw = get_setting('google_accounts')
    return json.loads(raw) if raw else []

def _save_accounts(accounts: list):
    set_setting('google_accounts', json.dumps(accounts))

def is_authenticated() -> bool:
    return len(get_connected_accounts()) > 0

def get_connected_accounts() -> list:
    accounts = _get_accounts()
    if not accounts:
        legacy = get_setting('google_tokens')
        if legacy:
            data = json.loads(legacy)
            if 'email' not in data:
                data['email'] = 'Primary account'
            data.setdefault('calendar_id', 'primary')
            accounts = [data]
            _save_accounts(accounts)
    return accounts

def remove_account(email: str):
    accounts = _get_accounts()
    _save_accounts([a for a in accounts if a.get('email') != email])

def set_account_calendar(email: str, calendar_id: str):
    accounts = _get_accounts()
    for a in accounts:
        if a.get('email') == email:
            a['calendar_id'] = calendar_id
    _save_accounts(accounts)

# ── Credentials ───────────────────────────────────────────────────────────────

def _make_credentials(data: dict) -> Credentials:
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=data.get('client_id', os.environ.get('GOOGLE_CLIENT_ID')),
        client_secret=data.get('client_secret', os.environ.get('GOOGLE_CLIENT_SECRET')),
        scopes=data.get('scopes', SCOPES),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data['token'] = creds.token
        accounts = _get_accounts()
        for a in accounts:
            if a.get('email') == data.get('email'):
                a['token'] = creds.token
        _save_accounts(accounts)
    return creds

# ── Calendar operations ───────────────────────────────────────────────────────

def list_calendars() -> list:
    accounts = get_connected_accounts()
    if not accounts:
        raise RuntimeError('Not authenticated with Google')
    creds = _make_credentials(accounts[0])
    service = build('calendar', 'v3', credentials=creds)
    return service.calendarList().list().execute().get('items', [])

def _build_event_body(event_data: dict) -> dict:
    local_tz = str(datetime.now().astimezone().tzinfo)
    if event_data.get('allDay'):
        start = {'date': event_data['start'][:10]}
        end = {'date': (event_data.get('end') or event_data['start'])[:10]}
    else:
        start = {'dateTime': event_data['start'], 'timeZone': local_tz}
        end = {'dateTime': event_data['end'], 'timeZone': local_tz}

    body = {
        'summary': event_data['title'],
        'start': start,
        'end': end,
        'reminders': {'useDefault': True},
    }
    if event_data.get('location'):
        body['location'] = event_data['location']
    if event_data.get('description'):
        body['description'] = event_data['description']
    return body

def create_calendar_event(event_data: dict) -> dict:
    accounts = get_connected_accounts()
    if not accounts:
        raise RuntimeError('Not authenticated with Google — connect at least one account')

    body = _build_event_body(event_data)
    results = []

    for account in accounts:
        try:
            creds = _make_credentials(account)
            calendar_id = account.get('calendar_id') or 'primary'
            service = build('calendar', 'v3', credentials=creds)
            result = service.events().insert(calendarId=calendar_id, body=body).execute()
            results.append({'email': account.get('email'), 'id': result['id'], 'link': result.get('htmlLink', '')})
            print(f"[Calendar] Added event for {account.get('email')}")
        except Exception as e:
            print(f"[Calendar] Failed for {account.get('email')}: {e}")

    if not results:
        raise RuntimeError('Failed to add event to any calendar')

    return {'id': results[0]['id'], 'link': results[0]['link'], 'all': results}
