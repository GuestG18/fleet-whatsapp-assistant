import os
import html

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


async def get_today_trips(whatsapp_user: str):
    url = f"{FLEET_API_URL}/api/assistant/v1/trips/today"

    headers = {
        "X-Assistant-Token": FLEET_ASSISTANT_API_TOKEN,
        "X-Assistant-Provider": "whatsapp",
        "X-Assistant-User": whatsapp_user,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            url,
            headers=headers
        )

        response.raise_for_status()

        return response.json()


def format_today_trips(data: dict) -> str:
    trips = data.get("trips", [])
    count = len(trips)

    if count == 0:
        return "Nu există curse active astăzi."

    lines = [
        f"Curse active astăzi: {count}",
        ""
    ]

    for index, trip in enumerate(trips, start=1):
        vehicle = trip.get("vehicle") or "-"
        route = trip.get("route") or "-"
        driver = trip.get("driver") or "-"
        start = trip.get("start") or "-"
        status = trip.get("status") or "-"

        lines.append(
            f"{index}. {vehicle}"
        )
        lines.append(
            f"Ruta: {route}"
        )
        lines.append(
            f"Șofer: {driver}"
        )
        lines.append(
            f"Start: {start}"
        )
        lines.append(
            f"Status: {status}"
        )
        lines.append("")

    return "\n".join(lines).strip()


def twiml(message: str):
    safe_message = html.escape(message)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe_message}</Message>
</Response>"""

    return Response(
        content=xml,
        media_type="application/xml"
    )


@app.post("/whatsapp")
async def whatsapp(
    Body: str = Form(""),
    From: str = Form("")
):
    message = Body.strip().lower()

    today_commands = {
        "ce curse am azi",
        "ce curse am azi?",
        "ce curse sunt azi",
        "curse azi",
        "cursele de azi",
        "cursele mele azi",
        "ce curse am astazi",
        "arată cursele de azi",
        "arata cursele de azi",
    }

    try:
        if message in today_commands:
            data = await get_today_trips(From)
            reply = format_today_trips(data)

        elif message in {
            "salut",
            "hello",
            "hi"
        }:
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
        status = exc.response.status_code

        if status == 401:
            reply = "Fleet Assistant nu este autorizat să acceseze Fleet App."

        elif status == 403:
            reply = "Nu ai permisiunea necesară pentru această informație."

        elif status == 404:
            reply = "Numărul tău WhatsApp nu este asociat unui utilizator Fleet."

        else:
            reply = "Fleet App nu poate răspunde momentan."

    except httpx.RequestError:
        reply = "Nu mă pot conecta momentan la Fleet App."

    except Exception:
        reply = "A apărut o eroare temporară în Fleet Assistant."

    return twiml(reply)
