import os
import httpx

from fastapi import FastAPI, Form
from fastapi.responses import Response


app = FastAPI()

FLEET_API_URL = os.getenv("FLEET_API_URL", "")
FLEET_API_TOKEN = os.getenv("FLEET_API_TOKEN", "")


@app.get("/")
def root():
    return {
        "status": "Fleet Assistant online"
    }


async def get_today_trips(whatsapp_user: str):

    url = f"{FLEET_API_URL}/api/assistant/v1/trips/today"

    headers = {
        "X-Assistant-Token": FLEET_API_TOKEN,
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


def trips_to_message(data: dict) -> str:

    count = data.get("count", 0)

    if count == 0:
        return "Nu ai curse programate pentru astăzi."

    employee = data.get("employee", {})
    employee_name = employee.get("name", "")

    lines = []

    if employee_name:
        lines.append(
            f"{employee_name}, ai {count} curse astăzi:"
        )
    else:
        lines.append(
            f"Ai {count} curse astăzi:"
        )

    lines.append("")

    for index, trip in enumerate(
        data.get("trips", []),
        start=1
    ):
        lines.append(
            f"{index}. {trip.get('route', '-')}"
        )

        lines.append(
            f"🚛 {trip.get('vehicle', '-')}"
        )

        lines.append(
            f"🕐 {trip.get('start', '-')}"
        )

        lines.append(
            f"Status: {trip.get('status', '-')}"
        )

        lines.append("")

    return "\n".join(lines)


@app.post("/whatsapp")
async def whatsapp(
    Body: str = Form(""),
    From: str = Form("")
):

    message = Body.strip().lower()

    try:

        if message in {
            "ce curse am azi",
            "curse azi",
            "cursele mele azi",
            "ce curse am astazi",
            "cursele de azi"
        }:

            data = await get_today_trips(From)

            reply = trips_to_message(data)

        elif message in {
            "salut",
            "hello",
            "hi"
        }:

            reply = (
                "Salut! Sunt Fleet Assistant.\n\n"
                "Pentru început poți întreba:\n"
                "\"Ce curse am azi?\""
            )

        else:

            reply = (
                "Momentan sunt în modul de test.\n\n"
                "Încearcă:\n"
                "\"Ce curse am azi?\""
            )

    except httpx.HTTPStatusError as exc:

        if exc.response.status_code == 404:
            reply = (
                "Numărul tău WhatsApp nu este "
                "asociat încă unui utilizator Fleet."
            )

        elif exc.response.status_code == 403:
            reply = (
                "Nu ai permisiunea necesară "
                "pentru această informație."
            )

        else:
            reply = (
                "Fleet Assistant nu poate accesa "
                "datele momentan."
            )

    except Exception:
        reply = (
            "A apărut o eroare temporară în Fleet Assistant."
        )

    xml = f"""
    <Response>
        <Message>{reply}</Message>
    </Response>
    """

    return Response(
        content=xml,
        media_type="application/xml"
    )
