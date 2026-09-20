"""
Receipt emails for MCP Builder.

The amounts are computed here from the build itself, never taken from the client, and the only
free text that reaches the message is the validated server name and order id. The message carries
the generated server as a .zip so a closed browser tab never loses a download.
"""

import base64
import io
import smtplib
import ssl
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx

PRICES = {"files": 5.00, "database": 15.00, "api": 20.00}
PROMO_CODES = {"LAUNCH20": 0.20}

_TEXT = {
    "en": {
        "subject": "Your MCP Builder receipt {order}",
        "greeting": "Hello,",
        "intro": "Thank you for trying MCP Builder. Here is your receipt.",
        "order": "Order",
        "date": "Date",
        "product": "Product",
        "server": "Server",
        "price": "Price",
        "discount": "Discount",
        "none": "None",
        "total": "Total",
        "demo": "This is a demo: no charge was made.",
        "attachment": "Your server is attached as {name}.zip. Unzip it, run npm install and npm run build, and follow the README.md inside.",
        "products": {"files": "MCP server - Local Files", "database": "MCP server - Database", "api": "MCP server - External API"},
    },
    "de": {
        "subject": "Ihre MCP-Builder-Quittung {order}",
        "greeting": "Guten Tag,",
        "intro": "Vielen Dank, dass Sie MCP Builder ausprobiert haben. Hier ist Ihre Quittung.",
        "order": "Bestellung",
        "date": "Datum",
        "product": "Produkt",
        "server": "Server",
        "price": "Preis",
        "discount": "Rabatt",
        "none": "Keiner",
        "total": "Gesamt",
        "demo": "Dies ist eine Demo: Es wurde nichts abgebucht.",
        "attachment": "Ihr Server ist als {name}.zip angehängt. Entpacken Sie ihn, führen Sie npm install und npm run build aus und folgen Sie der README.md darin.",
        "products": {"files": "MCP-Server - Lokale Dateien", "database": "MCP-Server - Datenbank", "api": "MCP-Server - Externe API"},
    },
    "es": {
        "subject": "Tu recibo de MCP Builder {order}",
        "greeting": "Hola,",
        "intro": "Gracias por probar MCP Builder. Este es tu recibo.",
        "order": "Pedido",
        "date": "Fecha",
        "product": "Producto",
        "server": "Servidor",
        "price": "Precio",
        "discount": "Descuento",
        "none": "Ninguno",
        "total": "Total",
        "demo": "Esto es una demostración: no se cobró nada.",
        "attachment": "Tu servidor va adjunto como {name}.zip. Descomprímelo, ejecuta npm install y npm run build, y sigue el README.md que trae dentro.",
        "products": {"files": "Servidor MCP - Archivos locales", "database": "Servidor MCP - Base de datos", "api": "Servidor MCP - API externa"},
    },
}


def build_zip(files: dict[str, str], folder: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(f"{folder}/{name}", content)
    return buffer.getvalue()


def compose_receipt(
    language: str,
    server_name: str,
    source: str,
    order_id: str,
    discount_code: str | None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Returns (subject, plain text body)."""
    text = _TEXT[language]
    price = PRICES[source]
    rate = PROMO_CODES.get((discount_code or "").upper(), 0.0)
    total = price * (1 - rate)
    when = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    discount = f"{(discount_code or '').upper()} (-{round(rate * 100)}%)" if rate else text["none"]
    lines = [
        text["greeting"],
        "",
        text["intro"],
        "",
        f"{text['order']}: #{order_id}",
        f"{text['date']}: {when}",
        f"{text['product']}: {text['products'][source]}",
        f"{text['server']}: {server_name}",
        f"{text['price']}: ${price:.2f}",
        f"{text['discount']}: {discount}",
        f"{text['total']}: ${total:.2f}",
        "",
        text["demo"],
        text["attachment"].format(name=server_name),
        "",
        "MCP Builder",
    ]
    return text["subject"].format(order=f"#{order_id}"), "\n".join(lines) + "\n"


def send_email(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    sender: str,
    security: str,
    to: str,
    subject: str,
    body: str,
    attachment: tuple[str, bytes] | None,
    reply_to: str | None = None,
) -> None:
    """Blocking SMTP send. Run it in a thread. Header values cannot contain newlines."""
    message = EmailMessage()
    message["From"] = sender if "<" in sender else formataddr(("MCP Builder", sender))
    message["To"] = to
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    message["Message-ID"] = make_msgid(domain=sender.split("@")[-1].strip("> "))
    message.set_content(body)
    if attachment:
        message.add_attachment(attachment[1], maintype="application", subtype="zip", filename=attachment[0])

    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if security == "starttls":
                smtp.starttls(context=context)
            if user:
                smtp.login(user, password)
            smtp.send_message(message)


async def send_with_resend(
    http: httpx.AsyncClient,
    *,
    api_key: str,
    sender: str,
    to: str,
    subject: str,
    body: str,
    attachment: tuple[str, bytes] | None,
    reply_to: str | None = None,
) -> None:
    """Sends through the Resend HTTPS API. Hosts that block SMTP ports can still use it."""
    payload: dict = {
        "from": sender if "<" in sender else formataddr(("MCP Builder", sender)),
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if attachment:
        payload["attachments"] = [{"filename": attachment[0], "content": base64.b64encode(attachment[1]).decode()}]
    response = await http.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=20.0,
    )
    response.raise_for_status()
