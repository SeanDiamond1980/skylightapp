import os
import threading
import time
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, redirect, send_from_directory

from database import get_events, get_event, get_setting, set_setting
from calendar_service import (get_auth_url, exchange_code_for_tokens, is_authenticated,
                               list_calendars, get_connected_accounts, remove_account, set_account_calendar)
from processor import process_email_payload
from gmail_poller import poll_gmail

app = Flask(__name__, static_folder='public', static_url_path='')

# ── Static / index ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# ── Google OAuth ──────────────────────────────────────────────────────────────

@app.route('/auth/google')
def auth_google():
    return redirect(get_auth_url())

@app.route('/auth/callback')
def auth_callback():
    error = request.args.get('error')
    if error:
        return redirect(f'/?auth=error&reason={error}')
    code = request.args.get('code')
    try:
        exchange_code_for_tokens(code)
        return redirect('/?auth=success')
    except Exception as e:
        return redirect(f'/?auth=error&reason={str(e)}')

# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/api/status')
def api_status():
    accounts = get_connected_accounts()
    google_authed = len(accounts) > 0
    calendars = []
    if google_authed:
        try:
            raw = list_calendars()
            calendars = [{'id': c['id'], 'summary': c.get('summary', c['id'])} for c in raw]
        except Exception:
            pass

    return jsonify({
        'googleAuthed': google_authed,
        'connectedAccounts': [{'email': a.get('email'), 'calendarId': a.get('calendar_id', 'primary')} for a in accounts],
        'calendars': calendars,
        'calendarId': os.environ.get('DEFAULT_CALENDAR_ID') or get_setting('calendar_id') or 'primary',
        'anthropicConfigured': bool(os.environ.get('ANTHROPIC_API_KEY')),
        'gmailPolling': bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD')),
        'pollInterval': int(os.environ.get('POLL_INTERVAL_MINUTES', '5')),
    })

@app.route('/api/accounts', methods=['GET'])
def api_accounts():
    accounts = get_connected_accounts()
    return jsonify([{'email': a.get('email'), 'calendarId': a.get('calendar_id', 'primary')} for a in accounts])

@app.route('/api/accounts/<path:email>', methods=['DELETE'])
def api_remove_account(email):
    remove_account(email)
    return jsonify({'ok': True})

@app.route('/api/accounts/<path:email>/calendar', methods=['POST'])
def api_set_account_calendar(email):
    data = request.get_json() or {}
    calendar_id = data.get('calendarId', 'primary')
    set_account_calendar(email, calendar_id)
    return jsonify({'ok': True})

@app.route('/api/events')
def api_events():
    return jsonify(get_events(100))

@app.route('/api/events/<int:event_id>')
def api_event(event_id):
    ev = get_event(event_id)
    if not ev:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(ev)

@app.route('/api/process', methods=['POST'])
def api_process():
    data = request.get_json() or {}
    subject = data.get('subject', '').strip()
    from_addr = data.get('from', '').strip()
    body = data.get('body', '').strip()

    if not body and not subject:
        return jsonify({'error': 'Provide at least body or subject'}), 400

    try:
        result = process_email_payload(subject=subject, from_addr=from_addr, body=body, source='manual')
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 422

@app.route('/webhook/email', methods=['POST'])
def webhook_email():
    # Validate optional secret
    secret = os.environ.get('WEBHOOK_SECRET')
    if secret:
        provided = request.headers.get('X-Webhook-Secret') or request.args.get('secret')
        if provided != secret:
            return jsonify({'error': 'Unauthorized'}), 401

    # Normalise across Mailgun / Postmark / SendGrid
    data = request.get_json(silent=True) or request.form.to_dict()
    subject = (data.get('subject') or data.get('Subject') or '').strip()
    from_addr = (data.get('from') or data.get('From') or data.get('sender') or '').strip()
    body = (
        data.get('body-plain') or data.get('text') or data.get('TextBody')
        or data.get('plain') or data.get('body') or ''
    ).strip()

    if not body and not subject:
        return jsonify({'error': 'No email content found'}), 400

    try:
        result = process_email_payload(subject=subject, from_addr=from_addr, body=body, source='webhook')
        return jsonify({'ok': True, 'id': result['id']})
    except Exception as e:
        return jsonify({'error': str(e)}), 422

@app.route('/api/settings/calendar', methods=['POST'])
def api_save_calendar():
    data = request.get_json() or {}
    calendar_id = data.get('calendarId', '').strip()
    if not calendar_id:
        return jsonify({'error': 'calendarId required'}), 400
    set_setting('calendar_id', calendar_id)
    os.environ['DEFAULT_CALENDAR_ID'] = calendar_id
    return jsonify({'ok': True})

@app.route('/api/poll', methods=['POST'])
def api_poll():
    threading.Thread(target=poll_gmail, daemon=True).start()
    return jsonify({'ok': True, 'message': 'Gmail poll triggered'})

# ── Gmail background polling ──────────────────────────────────────────────────

def _start_poller():
    interval = int(os.environ.get('POLL_INTERVAL_MINUTES', '5')) * 60
    if interval <= 0:
        return
    if not (os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD')):
        return

    def loop():
        while True:
            time.sleep(interval)
            print('[Cron] Polling Gmail...')
            poll_gmail()

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    print(f'[Cron] Gmail polling every {interval // 60} min')

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    _start_poller()

    print(f'\n🗓  Skylight Calendar Applet running at http://localhost:{port}\n')
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('  ⚠  ANTHROPIC_API_KEY not set')
    if not is_authenticated():
        print('  ⚠  Google Calendar not connected — visit /auth/google\n')

    app.run(host='0.0.0.0', port=port, debug=False)
