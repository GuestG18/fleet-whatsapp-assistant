from fastapi import FastAPI, Form
from fastapi.responses import Response

app = FastAPI()


@app.get("/")
def root():
    return {"status": "Fleet Assistant online"}


@app.post("/whatsapp")
async def whatsapp(
    Body: str = Form(""),
    From: str = Form("")
):
    print("From:", From)
    print("Message:", Body)

    xml = f"""
    <Response>
        <Message>Fleet Assistant is online. Ai trimis: {Body}</Message>
    </Response>
    """

    return Response(
        content=xml,
        media_type="application/xml"
    )
