from database import insert_event, update_event
from event_parser import parse_event_from_email
from calendar_service import create_calendar_event


def process_email_payload(subject: str = '', from_addr: str = '', body: str = '', source: str = 'manual') -> dict:
    row_id = insert_event({
        'email_subject': subject,
        'email_from': from_addr,
        'email_body': body,
        'source': source,
        'status': 'parsing',
        'parsed_title': None,
        'parsed_start': None,
        'parsed_end': None,
        'parsed_location': None,
        'parsed_description': None,
        'calendar_event_id': None,
        'calendar_event_link': None,
        'error': None,
    })

    try:
        parsed = parse_event_from_email(subject=subject, from_addr=from_addr, body=body)

        update_event(row_id, {
            'parsed_title': parsed.get('title'),
            'parsed_start': parsed.get('start'),
            'parsed_end': parsed.get('end'),
            'parsed_location': parsed.get('location'),
            'parsed_description': parsed.get('description'),
            'status': 'parsed',
        })

        cal_event = create_calendar_event(parsed)

        update_event(row_id, {
            'calendar_event_id': cal_event['id'],
            'calendar_event_link': cal_event['link'],
            'status': 'added',
        })

        return {'id': row_id, 'status': 'added', 'event': parsed, 'calEvent': cal_event}

    except Exception as e:
        update_event(row_id, {'status': 'error', 'error': str(e)})
        raise
