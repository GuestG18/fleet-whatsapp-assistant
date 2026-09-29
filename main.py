import os
import re
import html
import unicodedata

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


@app.get("/")
def root():
    return {
        "status": "Fleet Assistant online"
    }


def normalize_message(text: str) -> str:
    """
    Normalizează mesajele astfel încât:
    - să ignore litere mari/mici
    - să ignore diacriticele
    - să ignore semnele de punctuație
    - să ignore spațiile multiple
    """

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


def format_today_trips(
    data: dict
) -> str:

    trips = data.get(
        "trips",
        []
    )

    count = data.get(
        "count",
        len(trips)
    )

    if not trips:
        return (
            "Nu există curse active "
            "pentru astăzi."
        )

    lines = [
        f"Curse active astăzi: {count}",
        ""
    ]

    for index, trip in enumerate(
        trips,
        start=1
    ):

        vehicle = (
            trip.get("vehicle")
            or "-"
        )

        route = (
            trip.get("route")
            or "-"
        )

        driver = (
            trip.get("driver")
            or "-"
        )

        start = (
            trip.get("start")
            or "-"
        )

        status = (
            trip.get("status")
            or "-"
        )

        start_date = (
            trip.get("start_date")
            or ""
        )

        lines.append(
            f"{index}. {vehicle}"
        )

        lines.append(
            f"Ruta: {route}"
        )

        lines.append(
            f"Șofer: {driver}"
        )

        if start_date:
            lines.append(
                f"Start: {start_date} {start}"
            )
        else:
            lines.append(
                f"Start: {start}"
            )

        lines.append(
            f"Status: {status}"
        )

        lines.append("")

    return "\n".join(
        lines
    ).strip()


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

            reply = format_today_trips(
                data
            )

        elif message in greeting_commands:

            reply = (
                "Salut! Sunt Fleet Assistant.\n\n"
                "Momentan poți încerca:\n"
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
                "autorizat să acceseze "
                "Fleet App."
            )

        elif status_code == 403:

            reply = (
                "Nu ai permisiunea "
                "necesară pentru această "
                "informație."
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
