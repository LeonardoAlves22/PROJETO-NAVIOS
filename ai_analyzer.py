import re
import json
import requests
from datetime import datetime, timedelta
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_URL, BR_TZ


def _call_openrouter(system_prompt, user_content, max_tokens=200):
    if not OPENROUTER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://monitor-ws.streamlit.app",
        "X-Title": "Monitor WS"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }

    for attempt in range(2):
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == 0:
                    import time
                    time.sleep(2)
                    continue
                return None
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            if attempt == 0:
                continue
            return None
    return None


def _clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _validate_date(date_str):
    if not date_str or date_str == "-":
        return "-"
    try:
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            d, m, a = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            d, m = int(parts[0]), int(parts[1])
            a = datetime.now(BR_TZ).year
        else:
            return "-"

        dt = datetime(a, m, d, tzinfo=BR_TZ)
        hoje = datetime.now(BR_TZ).replace(hour=0, minute=0, second=0, microsecond=0)

        if dt < (hoje - timedelta(days=15)):
            return "-"
        if dt > (hoje + timedelta(days=90)):
            return "-"

        return f"{d:02d}/{m:02d}/{a}"
    except Exception:
        return "-"


def _parse_ai_response(raw):
    if not raw:
        return None
    try:
        cleaned = raw.strip()
        # Extrair JSON se vier dentro de ```json ... ```
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)
        # Ou pegar o primeiro { ... }
        elif not cleaned.startswith("{"):
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
        return json.loads(cleaned)
    except Exception:
        return None


PROSPECT_SYSTEM_PROMPT = """You are an expert maritime shipping email analyst. Extract date information from the following prospect/operational email for the vessel "{ship_name}".

Extract these fields:
- ETA (Estimated Time of Arrival): Look for "ETA", "arrival at roads", "notice of readiness", "NOR tendered", "ETA at Mosqueiro", "ETA at Vila do Conde", "expected arrival"
- ETB (Estimated Time of Berthing): Look for "ETB", "berthed", "all fast", "alongside", "expected berthing"
- ETD (Estimated Time of Departure/Sailing): Look for "ETD", "ETC", "ETS", "ETD/s", "ETC/s", "estimated time for sailing", "estimated completion", "expected sailing", "expected departure"

Rules:
- Return dates in DD/MM/YYYY format
- If only day and month are present, assume year {current_year}
- If a field is not found in the email, return "-"
- Only extract dates, not times
- If the email mentions a date range, use the earliest date

Return ONLY a valid JSON object: {{"ETA": "...", "ETB": "...", "ETD": "..."}}"""


APPOINTMENT_SYSTEM_PROMPT = """You are a maritime shipping analyst. This email may contain a new ship agency appointment or nomination.

Extract:
- ship_name: The vessel name (without MV/M/V/MT/M/T prefix, uppercase)
- port: The port. Use "SLZ" for São Luís/SLZ/Maranhão/Itaqui, "BEL" for Belém/BEL/Pará/Vila do Conde/Barcarena, or "UNKNOWN" if unclear
- is_appointment: true if this is indeed a new appointment/nomination/apontamento, false otherwise

Return ONLY a valid JSON object: {"ship_name": "...", "port": "...", "is_appointment": true/false}"""


def analyze_prospect_email(email_body, ship_name):
    default = {"ETA": "-", "ETB": "-", "ETD": "-"}

    if not email_body or not OPENROUTER_API_KEY:
        return default

    cleaned = _clean_html(email_body)
    if len(cleaned) < 20:
        return default

    # Truncar para economizar tokens
    truncated = cleaned[:3000]

    current_year = datetime.now(BR_TZ).year
    prompt = PROSPECT_SYSTEM_PROMPT.format(ship_name=ship_name, current_year=current_year)

    raw = _call_openrouter(prompt, truncated)
    parsed = _parse_ai_response(raw)

    if not parsed:
        return default

    return {
        "ETA": _validate_date(parsed.get("ETA", "-")),
        "ETB": _validate_date(parsed.get("ETB", "-")),
        "ETD": _validate_date(parsed.get("ETD", "-")),
    }


def detect_appointment(email_subject, email_body):
    if not email_subject and not email_body:
        return None
    if not OPENROUTER_API_KEY:
        return None

    # Pré-filtro
    combined = (email_subject + " " + (email_body or "")[:500]).upper()
    appointment_terms = ["APPOINTMENT", "NOMINATION", "APONTAMENTO", "NOMEACAO", "NOMEAÇÃO", "AGENCY APPOINT"]
    if not any(term in combined for term in appointment_terms):
        return None

    cleaned_body = _clean_html(email_body or "")[:2000]
    content = f"Subject: {email_subject}\n\nBody:\n{cleaned_body}"

    raw = _call_openrouter(APPOINTMENT_SYSTEM_PROMPT, content)
    parsed = _parse_ai_response(raw)

    if not parsed:
        return None

    if parsed.get("is_appointment") is True and parsed.get("ship_name"):
        return {
            "ship_name": parsed["ship_name"].upper().strip(),
            "port": parsed.get("port", "UNKNOWN"),
        }

    return None


def detect_clp(email_subject):
    if not email_subject:
        return False
    subj = email_subject.upper()
    return any(term in subj for term in ["FREE PRATIQUE", "LIVRE PRÁTICA", "LIVRE PRATICA", "CLP EMITIDA"])
