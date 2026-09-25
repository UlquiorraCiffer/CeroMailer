from http.server import BaseHTTPRequestHandler
import json
import os
import re
import smtplib
import mimetypes
from email.message import EmailMessage
from email.utils import formataddr
from datetime import datetime, timedelta, timezone
from supabase import create_client

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def strip_newlines(value):
    return (value or "").replace("\r", "").replace("\n", "")


# Vercel's Python runtime looks for a class named exactly "handler"
class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {})

    def do_POST(self):
        ip = self.headers.get("x-forwarded-for", "").split(",")[0].strip() or self.client_address[0]

        # --- 1. Rate limit: max 5 requests per IP in a 3 second window ---
        three_seconds_ago = (datetime.now(timezone.utc) - timedelta(seconds=3)).isoformat()
        recent = (
            supabase.table("send_logs")
            .select("id")
            .eq("ip_address", ip)
            .gte("created_at", three_seconds_ago)
            .execute()
        )
        if len(recent.data) >= 5:
            return self._send_json(429, {"error": "Too many requests, slow down"})

        # --- 2. Daily cap: stop at 400 sends/day, well under Gmail's ~500 limit ---
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        today = (
            supabase.table("send_logs")
            .select("id", count="exact")
            .gte("created_at", start_of_day)
            .execute()
        )
        if (today.count or 0) >= 400:
            return self._send_json(429, {"error": "Daily limit reached, try tomorrow"})

        # --- 3. Read and sanitize input ---
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "Invalid JSON"})

        receiver = strip_newlines(data.get("receiver"))
        subject = strip_newlines(data.get("subject")) or "(no subject)"
        body_text = data.get("body", "")
        file_paths = data.get("filePaths") or []

        if not EMAIL_REGEX.match(receiver):
            return self._send_json(400, {"error": "Invalid receiver email address"})

        # --- 4. Fetch files from Supabase Storage (uploaded there by the client) ---
        attachments = []  # list of (file_name, file_bytes) tuples
        for fp in file_paths:
            try:
                fb = supabase.storage.from_("uploads").download(fp)
                fn = fp.split("/")[-1]
                attachments.append((fn, fb))
            except Exception:
                return self._send_json(400, {"error": f"Could not fetch uploaded file: {fp}"})

        # --- 5. Build and send the email — same pattern as testmail.py ---
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr(("Cero Mailer", GMAIL_USER))
        msg["To"] = receiver
        msg.set_content(body_text)

        for file_name, file_bytes in attachments:
            mime_type, _ = mimetypes.guess_type(file_name)
            if mime_type is None:
                mime_type = "application/octet-stream"
            main_type, sub_type = mime_type.split("/")
            msg.add_attachment(file_bytes, maintype=main_type, subtype=sub_type, filename=file_name)

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                server.send_message(msg)
        except Exception:
            return self._send_json(500, {"error": "Failed to send email"})

        # --- 6. Log the send, then clean up the temp files ---
        logged_names = ", ".join(fn for fn, _ in attachments) or None
        supabase.table("send_logs").insert(
            {"ip_address": ip, "receiver": receiver, "file_name": logged_names}
        ).execute()

        if file_paths:
            supabase.storage.from_("uploads").remove(file_paths)

        return self._send_json(200, {"success": True})
