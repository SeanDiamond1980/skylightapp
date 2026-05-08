import json
import re
from datetime import date
import anthropic

_client = None

def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client

SYSTEM_PROMPT = f"""You are an expert at extracting calendar event details from emails and text.
Your job is to parse event information and return it as structured JSON.

Always return a JSON object with these fields:
- title: string (concise event name, required)
- start: string (ISO 8601 datetime, e.g. "2026-05-15T14:00:00" — required)
- end: string (ISO 8601 datetime — if not specified, assume 1 hour after start)
- allDay: boolean (true if no specific time is mentioned)
- location: string or null (physical address, venue name, or video link)
- description: string (brief summary including key details like dress code, RSVP, ticket info)
- organizer: string or null (person or organization hosting)
- confidence: number 0-1 (how confident you are in the extraction)
- notes: string or null (anything ambiguous or that the user should know)

Rules:
- For relative dates like "this Saturday", use today's date ({date.today().isoformat()}) to calculate the absolute date
- If no year is given, infer from context (upcoming events)
- If the email contains multiple events, extract the FIRST/primary one
- If no event can be found, return {{ "error": "No event found", "confidence": 0 }}
- Return ONLY the JSON object, no markdown or explanation"""


def parse_event_from_email(subject: str = '', from_addr: str = '', body: str = '') -> dict:
    parts = []
    if subject:
        parts.append(f'Subject: {subject}')
    if from_addr:
        parts.append(f'From: {from_addr}')
    parts.append('')
    parts.append(body or '')
    email_text = '\n'.join(parts)

    message = get_client().messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            'role': 'user',
            'content': f'Extract the calendar event details from this email:\n\n{email_text}'
        }]
    )

    text = message.content[0].text.strip()
    # Strip markdown fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)

    parsed = json.loads(text.strip())

    if 'error' in parsed:
        raise ValueError(parsed['error'])

    return parsed
