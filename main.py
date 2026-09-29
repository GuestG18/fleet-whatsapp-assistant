import os
import re
import html
import unicodedata
from typing import Dict, List

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import Response


app = FastAPI()

FLEET_API_URL = os.getenv(
    "FLEET_API_URL",
    ""
).rstrip("/")

FLEET_ASSISTANT_API_TOKEN = os.getenv(
    "FLEET_ASSISTANT_API_TOKEN",
    ""
)

TRIPS_PER_PAGE = 6

# MVP: memorie în RAM.
# Cheie = numărul WhatsApp
# Valoare = datele ultimei liste + pagina curentă.
conversation_state: Dict[str, dict] = {}


@app.get("/")
def root():
    return {
        "status": "Fleet Assistant online"
    }


def normalize_message(text: str) -> str:
    text = text.strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


async def get_today_trips(
    whatsapp_user: str
) -> dict:

    if not FLEET_API_URL:
        raise RuntimeError(
            "FLEET_API_URL is not configured"
        )

    if not FLEET_ASSISTANT_API_TOKEN:
        raise RuntimeError(
            "FLEET_ASSISTANT_API_TOKEN is not configured"
        )

    url = (
        f"{FLEET_API_URL}"
        "/api/assistant/v1/trips/today"
    )

    headers = {
        "X-Assistant-Token": FLEET_ASSISTANT_API_TOKEN,
        "X-Assistant-Provider": "whatsapp",
        "X-Assistant-User": whatsapp_user,
    }

    async with httpx.AsyncClient(
        timeout=20.0
    ) as client:

        response = await client.get(
            url,
            headers=headers
        )

        response.raise_for_status()

        return response.json()


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
        f"{driver} · {start}",
    ]

    if start_date:
        lines[-1] = (
            f"{driver} · "
            f"{start_date} {start}"
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
            f"({start_index + 1}-{min(end_index, total)} "
            f"din {total})"
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


def twiml_response(
    message: str
) -> Response:

    safe_message = html.escape(
        message
    )

    xml = (
        '<?xml version="1.0" '
        'encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe_message}</Message>"
        "</Response>"
    )

    return Response(
        content=xml,
        media_type="application/xml"
    )


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

    try:

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

        elif message in more_commands:

            state = conversation_state.get(
                whatsapp_user
            )

            if not state:
                reply = (
                    "Nu am o listă activă pentru continuare.\n\n"
                    "Încearcă:\n"
                    "„Arată cursele de azi”"
                )

            elif state.get("type") == "today_trips":

                next_page = (
                    state.get("page", 0)
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
                    reply = (
                        "Nu mai sunt alte curse."
                    )

                else:
                    state["page"] = next_page

                    reply = format_trip_page(
                        trips,
                        next_page
                    )

        elif message in greeting_commands:

            reply = (
                "Salut! Sunt Fleet Assistant.\n\n"
                "Poți încerca:\n"
                "„Arată cursele de azi”"
            )

        else:

            reply = (
                "Momentan sunt în modul de test.\n\n"
                "Încearcă:\n"
                "„Arată cursele de azi”"
            )

    except httpx.HTTPStatusError as exc:

        status_code = (
            exc.response.status_code
        )

        print(
            "Fleet API HTTP error:",
            status_code
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

            reply = (
                "Numărul tău WhatsApp "
                "nu este asociat unui "
                "utilizator Fleet."
            )

        else:

            reply = (
                "Fleet App a returnat "
                "o eroare."
            )

    except httpx.RequestError as exc:

        print(
            "Fleet API connection error:",
            repr(exc)
        )

        reply = (
            "Nu mă pot conecta momentan "
            "la Fleet App."
        )

    except Exception as exc:

        print(
            "Unexpected error:",
            repr(exc)
        )

        reply = (
            "A apărut o eroare temporară "
            "în Fleet Assistant."
        )

    return twiml_response(
        reply
    )
