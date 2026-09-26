from http.server import BaseHTTPRequestHandler
import json
import os
import re
import smtplib
import ssl
import mimetypes
from email.message import EmailMessage
from email.utils import formataddr
from supabase import create_client

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ALLOWED_ORIGIN = os.environ["ALLOWED_ORIGIN"]

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

        # --- 1. Read and sanitize input ---
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "Invalid JSON"})

        receiver = strip_newlines(data.get("receiver"))
        subject = strip_newlines(data.get("subject")) or "(no subject)"
        body_text = data.get("body", "")
        session_id = data.get("sessionId")

        if not EMAIL_REGEX.match(receiver):
            return self._send_json(400, {"error": "Invalid receiver email address"})

        # --- 2. Fetch files from Supabase Storage under sessions/<sessionId>/ ---
        attachments = []  # list of (file_name, file_bytes) tuples
        file_paths = []
        if session_id and re.match(r"^[a-zA-Z0-9_-]+$", str(session_id)):
            try:
                listed_files = supabase.storage.from_("uploads").list(f"sessions/{session_id}")
                for item in listed_files:
                    fn = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
                    if not fn or fn == ".emptyFolderPlaceholder":
                        continue
                    fp = f"sessions/{session_id}/{fn}"
                    file_paths.append(fp)
                    fb = supabase.storage.from_("uploads").download(fp)
                    attachments.append((fn, fb))
            except Exception:
                return self._send_json(400, {"error": "Could not fetch uploaded session files"})

        # --- 3. Atomic rate limiting, daily cap check, and logging ---
        logged_names = ", ".join(fn for fn, _ in attachments) or None
        try:
            rpc_res = supabase.rpc(
                "check_and_log_send",
                {
                    "p_ip": ip,
                    "p_receiver": receiver,
                    "p_file_name": logged_names,
                },
            ).execute()
            if not rpc_res.data:
                return self._send_json(429, {"error": "Rate limit or daily limit reached, try later"})
        except Exception:
            return self._send_json(500, {"error": "Failed to verify rate limits"})

        # --- 4. Build and send the email ---
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
            ssl_context = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls(context=ssl_context)
                server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                server.send_message(msg)
        except Exception:
            return self._send_json(500, {"error": "Failed to send email"})

        # --- 5. Clean up uploaded temporary session files ---
        if file_paths:
            try:
                supabase.storage.from_("uploads").remove(file_paths)
            except Exception:
                pass

        return self._send_json(200, {"success": True})
