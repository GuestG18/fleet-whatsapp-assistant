import os
import re
import html
import unicodedata
from typing import Dict, List

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import Response


app = FastAPI()

FLEET_API_URL = os.getenv("FLEET_API_URL", "").rstrip("/")
FLEET_ASSISTANT_API_TOKEN = os.getenv("FLEET_ASSISTANT_API_TOKEN", "")

TRIPS_PER_PAGE = 6

# MVP: stare conversațională în RAM
conversation_state: Dict[str, dict] = {}


# =========================================================
# BASIC ROUTES
# =========================================================

@app.get("/")
def root():
    return {
        "status": "Fleet Assistant online"
    }


# =========================================================
# HELPERS
# =========================================================

def normalize_message(text: str) -> str:
    text = text.strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def twiml_response(message: str) -> Response:
    safe_message = html.escape(message)

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe_message}</Message>"
        "</Response>"
    )

    return Response(
        content=xml,
        media_type="application/xml"
    )


def twiml_media_response(
    message: str,
    media_url: str
) -> Response:

    safe_message = html.escape(message)
    safe_url = html.escape(media_url)

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Message>"
        f"<Body>{safe_message}</Body>"
        f"<Media>{safe_url}</Media>"
        "</Message>"
        "</Response>"
    )

    return Response(
        content=xml,
        media_type="application/xml"
    )


# =========================================================
# FLEET API
# =========================================================

def get_api_headers(whatsapp_user: str) -> dict:
    if not FLEET_ASSISTANT_API_TOKEN:
        raise RuntimeError(
            "FLEET_ASSISTANT_API_TOKEN is not configured"
        )

    return {
        "X-Assistant-Token": FLEET_ASSISTANT_API_TOKEN,
        "X-Assistant-Provider": "whatsapp",
        "X-Assistant-User": whatsapp_user,
    }


async def get_today_trips(
    whatsapp_user: str
) -> dict:

    if not FLEET_API_URL:
        raise RuntimeError(
            "FLEET_API_URL is not configured"
        )

    url = (
        f"{FLEET_API_URL}"
        "/api/assistant/v1/trips/today"
    )

    headers = get_api_headers(
        whatsapp_user
    )

    async with httpx.AsyncClient(
        timeout=20.0
    ) as client:

        response = await client.get(
            url,
            headers=headers
        )

        response.raise_for_status()

        return response.json()


async def get_vehicle_document(
    whatsapp_user: str,
    vehicle: str,
    document_type: str
) -> dict:

    if not FLEET_API_URL:
        raise RuntimeError(
            "FLEET_API_URL is not configured"
        )

    url = (
        f"{FLEET_API_URL}"
        "/api/assistant/v1/vehicle-document"
    )

    headers = get_api_headers(
        whatsapp_user
    )

    params = {
        "vehicle": vehicle,
        "document_type": document_type,
    }

    async with httpx.AsyncClient(
        timeout=20.0
    ) as client:

        response = await client.get(
            url,
            headers=headers,
            params=params
        )

        response.raise_for_status()

        return response.json()


# =========================================================
# TRIPS FORMAT
# =========================================================

def format_trip(
    trip: dict,
    index: int
) -> List[str]:

    vehicle = trip.get("vehicle") or "-"
    route = trip.get("route") or "-"
    driver = trip.get("driver") or "-"
    start = trip.get("start") or "-"
    start_date = trip.get("start_date") or ""

    lines = [
        f"{index}. {vehicle}",
        route,
    ]

    if start_date:
        lines.append(
            f"{driver} · {start_date} {start}"
        )
    else:
        lines.append(
            f"{driver} · {start}"
        )

    return lines


def format_trip_page(
    trips: List[dict],
    page: int
) -> str:

    total = len(trips)

    start_index = page * TRIPS_PER_PAGE
    end_index = start_index + TRIPS_PER_PAGE

    current = trips[
        start_index:end_index
    ]

    if not current:
        return "Nu mai sunt alte curse."

    lines = []

    if page == 0:
        lines.append(
            f"🚛 Curse active astăzi: {total}"
        )
        lines.append("")
    else:
        lines.append(
            f"🚛 Continuare curse "
            f"({start_index + 1}-"
            f"{min(end_index, total)} din {total})"
        )
        lines.append("")

    for offset, trip in enumerate(
        current,
        start=start_index + 1
    ):
        lines.extend(
            format_trip(
                trip,
                offset
            )
        )
        lines.append("")

    remaining = total - end_index

    if remaining > 0:
        lines.append(
            f"Mai sunt {remaining} curse."
        )
        lines.append(
            'Scrie „mai multe” pentru continuare.'
        )
    else:
        lines.append(
            "Ai ajuns la finalul listei."
        )

    return "\n".join(lines).strip()


# =========================================================
# DOCUMENT PARSING
# =========================================================

SUPPORTED_DOCUMENTS = {
    "rca": "RCA",
    "itp": "ITP",
    "rovinieta": "Rovinieta",
    "rovinieta": "Rovinieta",
    "iprochim": "Iprochim",
}


def extract_document_request(
    message: str
):
    """
    Exemple acceptate:
    trimite rca b 219 net
    trimite-mi rca b 219 net
    trimite rca-ul b 219 net
    da-mi itp b219net
    vreau rovinieta b 219 net
    """

    patterns = [
        r"trimite(?: mi)?\s+(rca|itp|rovinieta|iprochim)(?: ul)?\s+(.*)",
        r"da mi\s+(rca|itp|rovinieta|iprochim)(?: ul)?\s+(.*)",
        r"vreau\s+(rca|itp|rovinieta|iprochim)(?: ul)?\s+(.*)",
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            message
        )

        if match:
            doc_key = match.group(1).strip()
            vehicle = match.group(2).strip()

            vehicle = normalize_vehicle(
                vehicle
            )

            return (
                SUPPORTED_DOCUMENTS[doc_key],
                vehicle
            )

    return None


def normalize_vehicle(vehicle: str) -> str:
    """
    B219NET -> B 219 NET
    B-219-NET -> B 219 NET
    B 219 NET -> B 219 NET
    """

    cleaned = (
        vehicle
        .upper()
        .replace("-", " ")
    )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned
    ).strip()

    compact = cleaned.replace(
        " ",
        ""
    )

    match = re.match(
        r"^([A-Z]{1,2})(\d+)([A-Z]{2,3})$",
        compact
    )

    if match:
        return (
            f"{match.group(1)} "
            f"{match.group(2)} "
            f"{match.group(3)}"
        )

    return cleaned


# =========================================================
# WHATSAPP WEBHOOK
# =========================================================

@app.post("/whatsapp")
async def whatsapp(
    Body: str = Form(""),
    From: str = Form("")
):

    raw_message = Body
    whatsapp_user = From.strip()

    message = normalize_message(
        raw_message
    )

    print(
        "RAW MESSAGE:",
        repr(raw_message)
    )

    print(
        "NORMALIZED MESSAGE:",
        repr(message)
    )

    print(
        "WHATSAPP USER:",
        repr(whatsapp_user)
    )

    # -----------------------------------------------------
    # DOCUMENT REQUEST
    # -----------------------------------------------------

    document_request = extract_document_request(
        message
    )

    try:

        if document_request:

            document_type, vehicle = document_request

            print(
                "DOCUMENT REQUEST:",
                document_type,
                vehicle
            )

            data = await get_vehicle_document(
                whatsapp_user,
                vehicle,
                document_type
            )

            document = data.get(
                "document",
                {}
            )

            media_url = document.get(
                "download_url"
            )

            if not media_url:
                return twiml_response(
                    "Documentul a fost găsit, "
                    "dar nu am primit linkul de descărcare."
                )

            doc_type = document.get(
                "type",
                document_type
            )

            vehicle_name = document.get(
                "vehicle",
                vehicle
            )

            valid_until = document.get(
                "valid_until"
            )

            text = (
                f"📄 {doc_type} pentru {vehicle_name}"
            )

            if valid_until:
                text += (
                    f"\nValabil până la: {valid_until}"
                )

            return twiml_media_response(
                text,
                media_url
            )

        # -------------------------------------------------
        # TODAY TRIPS
        # -------------------------------------------------

        today_commands = {
            "ce curse am azi",
            "ce curse sunt azi",
            "curse azi",
            "cursele de azi",
            "cursele mele azi",
            "ce curse am astazi",
            "arata cursele de azi",
            "arata mi cursele de azi",
            "arata curse azi",
        }

        more_commands = {
            "mai multe",
            "continua",
            "continuare",
            "urmatoarele",
            "urmatoarea pagina",
        }

        greeting_commands = {
            "salut",
            "hello",
            "hi",
            "buna",
            "buna ziua",
        }

        if message in today_commands:

            data = await get_today_trips(
                whatsapp_user
            )

            trips = data.get(
                "trips",
                []
            )

            conversation_state[
                whatsapp_user
            ] = {
                "type": "today_trips",
                "trips": trips,
                "page": 0,
            }

            reply = format_trip_page(
                trips,
                0
            )

            return twiml_response(
                reply
            )

        # -------------------------------------------------
        # MORE
        # -------------------------------------------------

        if message in more_commands:

            state = conversation_state.get(
                whatsapp_user
            )

            if not state:
                return twiml_response(
                    "Nu am o listă activă pentru continuare.\n\n"
                    "Încearcă:\n"
                    "„Arată cursele de azi”"
                )

            if state.get("type") == "today_trips":

                next_page = (
                    state.get(
                        "page",
                        0
                    )
                    + 1
                )

                trips = state.get(
                    "trips",
                    []
                )

                start_index = (
                    next_page
                    * TRIPS_PER_PAGE
                )

                if start_index >= len(trips):

                    return twiml_response(
                        "Nu mai sunt alte curse."
                    )

                state[
                    "page"
                ] = next_page

                reply = format_trip_page(
                    trips,
                    next_page
                )

                return twiml_response(
                    reply
                )

        # -------------------------------------------------
        # GREETING
        # -------------------------------------------------

        if message in greeting_commands:

            return twiml_response(
                "Salut! Sunt Fleet Assistant.\n\n"
                "Poți încerca:\n"
                "• Arată cursele de azi\n"
                "• Trimite-mi RCA B 219 NET\n"
                "• Trimite-mi ITP B 219 NET"
            )

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------

        return twiml_response(
            "Momentan sunt în modul de test.\n\n"
            "Poți încerca:\n"
            "• Arată cursele de azi\n"
            "• Trimite-mi RCA B 219 NET\n"
            "• Trimite-mi ITP B 219 NET\n"
            "• Trimite-mi Rovinieta B 219 NET\n"
            "• Trimite-mi Iprochim B 219 NET"
        )

    # =====================================================
    # ERROR HANDLING
    # =====================================================

    except httpx.HTTPStatusError as exc:

        status_code = (
            exc.response.status_code
        )

        print(
            "Fleet API HTTP error:",
            status_code
        )

        error_code = ""

        try:
            body = exc.response.json()
            error_code = body.get(
                "error",
                ""
            )
        except Exception:
            pass

        print(
            "Fleet API error code:",
            repr(error_code)
        )

        if status_code == 401:

            reply = (
                "Fleet Assistant nu este "
                "autorizat să acceseze Fleet App."
            )

        elif status_code == 403:

            reply = (
                "Nu ai permisiunea necesară "
                "pentru această informație."
            )

        elif status_code == 404:

            if error_code == "vehicle_not_found":

                reply = (
                    "Nu am găsit vehiculul solicitat."
                )

            elif error_code == "document_not_found":

                reply = (
                    "Vehiculul există, dar documentul "
                    "cerut nu este înregistrat."
                )

            elif error_code == "document_file_missing":

                reply = (
                    "Documentul este înregistrat, "
                    "dar fișierul nu este disponibil."
                )

            elif error_code == "assistant_user_not_found":

                reply = (
                    "Numărul tău WhatsApp nu este "
                    "asociat unui utilizator Fleet."
                )

            else:

                reply = (
                    "Informația solicitată "
                    "nu a fost găsită."
                )

        elif status_code == 410:

            reply = (
                "Linkul documentului a expirat. "
                "Cere documentul din nou."
            )

        else:

            reply = (
                "Fleet App a returnat "
                "o eroare."
            )

        return twiml_response(
            reply
        )

    except httpx.RequestError as exc:

        print(
            "Fleet API connection error:",
            repr(exc)
        )

        return twiml_response(
            "Nu mă pot conecta momentan "
            "la Fleet App."
        )

    except Exception as exc:

        print(
            "Unexpected error:",
            repr(exc)
        )

        return twiml_response(
            "A apărut o eroare temporară "
            "în Fleet Assistant."
        )
