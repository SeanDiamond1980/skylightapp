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

def get_auth_url() -> str:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback')
    )
    url, _ = flow.authorization_url(access_type='offline', prompt='consent')
    return url

def exchange_code_for_tokens(code: str) -> dict:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback')
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES,
    }
    set_setting('google_tokens', json.dumps(token_data))
    return token_data

def is_authenticated() -> bool:
    return bool(get_setting('google_tokens'))

def _get_credentials() -> Credentials | None:
    token_json = get_setting('google_tokens')
    if not token_json:
        return None
    data = json.loads(token_json)
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=data.get('client_id', os.environ.get('GOOGLE_CLIENT_ID')),
        client_secret=data.get('client_secret', os.environ.get('GOOGLE_CLIENT_SECRET')),
        scopes=data.get('scopes', SCOPES),
    )
    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data['token'] = creds.token
        set_setting('google_tokens', json.dumps(data))
    return creds

def list_calendars() -> list:
    creds = _get_credentials()
    if not creds:
        raise RuntimeError('Not authenticated with Google')
    service = build('calendar', 'v3', credentials=creds)
    result = service.calendarList().list().execute()
    return result.get('items', [])

def create_calendar_event(event_data: dict) -> dict:
    creds = _get_credentials()
    if not creds:
        raise RuntimeError('Not authenticated with Google')

    calendar_id = (
        os.environ.get('DEFAULT_CALENDAR_ID')
        or get_setting('calendar_id')
        or 'primary'
    )

    tz = datetime.now(timezone.utc).astimezone().tzname() or 'UTC'
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

    service = build('calendar', 'v3', credentials=creds)
    result = service.events().insert(calendarId=calendar_id, body=body).execute()
    return {'id': result['id'], 'link': result.get('htmlLink', '')}
