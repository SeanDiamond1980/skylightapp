import imaplib
import email
import os
import threading
from processor import process_email_payload

_lock = threading.Lock()
_last_uid = 0


def poll_gmail():
    global _last_uid

    user = os.environ.get('GMAIL_USER', '')
    password = os.environ.get('GMAIL_APP_PASSWORD', '')

    if not user or not password:
        print('[Gmail Poller] Skipped — GMAIL_USER or GMAIL_APP_PASSWORD not set')
        return

    if not _lock.acquire(blocking=False):
        print('[Gmail Poller] Already running, skipping')
        return

    try:
        _poll(user, password)
    except Exception as e:
        print(f'[Gmail Poller] Error: {e}')
    finally:
        _lock.release()


def _poll(user, password):
    global _last_uid

    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(user, password)

    try:
        # For a dedicated account every email is an event — just poll INBOX.
        # GMAIL_LABEL can override this for a shared account with a specific label.
        label = os.environ.get('GMAIL_LABEL', 'INBOX')
        mailbox = 'INBOX' if label.upper() == 'INBOX' else f'"{label}"'
        status, _ = mail.select(mailbox)
        if status != 'OK':
            print(f'[Gmail Poller] Mailbox "{label}" not found')
            return

        _, data = mail.search(None, 'UNSEEN')
        uids = data[0].split() if data[0] else []

        if not uids:
            return

        for uid in uids:
            uid_int = int(uid)
            if uid_int <= _last_uid:
                continue

            _, msg_data = mail.fetch(uid, '(RFC822)')
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = email.header.decode_header(msg.get('Subject', ''))[0]
            subject_text = (
                subject[0].decode(subject[1] or 'utf-8')
                if isinstance(subject[0], bytes)
                else subject[0]
            )
            from_addr = msg.get('From', '')

            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='replace')
                        break
            else:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='replace')

            try:
                process_email_payload(subject=subject_text, from_addr=from_addr, body=body, source='gmail')
                mail.store(uid, '+FLAGS', '\\Seen')
                _last_uid = max(_last_uid, uid_int)
                print(f'[Gmail Poller] Processed: {subject_text}')
            except Exception as e:
                print(f'[Gmail Poller] Failed to process "{subject_text}": {e}')

    finally:
        mail.logout()
