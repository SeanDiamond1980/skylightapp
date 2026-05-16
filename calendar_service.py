import json
import os
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from database import get_setting, set_setting

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

def _client_config():
    return {
        'web': {
            'client_id': os.environ['GOOGLE_CLIENT_ID'],
            'client_secret': os.environ['GOOGLE_CLIENT_SECRET'],
            'redirect_uris': [os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback')],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }

def get_auth_url() -> tuple:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback')
    )
    url, state = flow.authorization_url(access_type='offline', prompt='consent')
    return url, state

def _get_accounts() -> list:
    raw = get_setting('google_accounts')
    return json.loads(raw) if raw else []

def _save_accounts(accounts: list):
    set_setting('google_accounts', json.dumps(accounts))

def exchange_code_for_tokens(code: str, state: str = None) -> dict:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback'),
        state=state
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Get the email address for this account
    service = build('oauth2', 'v2', credentials=creds)
    user_info = service.userinfo().get().execute()
    email = user_info.get('email', 'unknown')

    token_data = {
        'email': email,
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES,
        'calendar_id': 'primary',
    }

    # Add or update this account in the list
    accounts = _get_accounts()
    accounts = [a for a in accounts if a.get('email') != email]  # remove old entry
    accounts.append(token_data)
    _save_accounts(accounts)

    # Keep legacy key for backwards compatibility
    set_setting('google_tokens', json.dumps(token_data))

    return token_data

def is_authenticated() -> bool:
    return len(_get_accounts()) > 0 or bool(get_setting('google_tokens'))

def get_connected_accounts() -> list:
    accounts = _get_accounts()
    # Migrate legacy single account if needed
    if not accounts:
        legacy = get_setting('google_tokens')
        if legacy:
            data = json.loads(legacy)
            if 'email' not in data:
                data['email'] = 'Primary account'
            data['calendar_id'] = data.get('calendar_id', 'primary')
            accounts = [data]
            _save_accounts(accounts)
    return accounts

def remove_account(email: str):
    accounts = _get_accounts()
    accounts = [a for a in accounts if a.get('email') != email]
    _save_accounts(accounts)

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
        # Update stored token
        accounts = _get_accounts()
        for a in accounts:
            if a.get('email') == data.get('email'):
                a['token'] = creds.token
        _save_accounts(accounts)
    return creds

def list_calendars() -> list:
    accounts = get_connected_accounts()
    if not accounts:
        raise RuntimeError('Not authenticated with Google')
    creds = _make_credentials(accounts[0])
    service = build('calendar', 'v3', credentials=creds)
    result = service.calendarList().list().execute()
    return result.get('items', [])

def set_account_calendar(email: str, calendar_id: str):
    accounts = _get_accounts()
    for a in accounts:
        if a.get('email') == email:
            a['calendar_id'] = calendar_id
    _save_accounts(accounts)

def _build_event_body(event_data: dict) -> dict:
    local_tz = str(datetime.now().astimezone().tzinfo)
    if event_data.get('allDay'):
        start = {'date': event_data['start'][:10]}
        end_date = (event_data.get('end') or event_data['start'])[:10]
        end = {'date': end_date}
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
            results.append({
                'email': account.get('email'),
                'id': result['id'],
                'link': result.get('htmlLink', '')
            })
        except Exception as e:
            print(f"[Calendar] Failed to add event for {account.get('email')}: {e}")

    if not results:
        raise RuntimeError('Failed to add event to any calendar')

    # Return primary result for backwards compatibility
    return {'id': results[0]['id'], 'link': results[0]['link'], 'all': results}
