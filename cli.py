import os
import sys
import time
import mimetypes
import requests

# Same values as index.html — safe to keep here, this is the public/anon key,
# not a secret. The actual Gmail credentials never leave Vercel.
SUPABASE_URL = "https://euduprorskqxcvecapfo.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_gxIe1B6z1ZGKecBOksly4w_H9nw1xFq"
VERCEL_API_URL = "https://cero-mailer.vercel.app/api/send"

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def upload_file(file_path):
    file_name = os.path.basename(file_path)
    remote_path = f"{int(time.time() * 1000)}_{file_name}"

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    with open(file_path, "rb") as f:
        file_data = f.read()

    upload_url = f"{SUPABASE_URL}/storage/v1/object/uploads/{remote_path}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": mime_type,
    }

    response = requests.post(upload_url, headers=headers, data=file_data)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"{response.status_code}: {response.text}")

    return remote_path


def send_email(receiver, subject, body, remote_path):
    payload = {
        "receiver": receiver,
        "subject": subject,
        "body": body,
        "filePath": remote_path,
    }
    return requests.post(VERCEL_API_URL, json=payload)


def main():
    print("=== Cero Mailer (CLI) ===")
    receiver = input("Receiver Gmail address: ").strip()
    subject = input("Subject: ").strip()
    body = input("Body: ").strip()
    file_path = input("Full path of file to attach: ").strip()

    if not os.path.isfile(file_path):
        print("File not found.")
        sys.exit(1)

    if os.path.getsize(file_path) > MAX_FILE_SIZE:
        print("File too large (max 50MB).")
        sys.exit(1)

    print("Uploading file...")
    try:
        remote_path = upload_file(file_path)
    except Exception as e:
        print(f"Upload failed: {e}")
        sys.exit(1)

    print("Sending email...")
    response = send_email(receiver, subject, body, remote_path)

    if response.ok:
        print("Email sent!")
    else:
        try:
            error = response.json().get("error", response.text)
        except ValueError:
            error = response.text
        print(f"Error: {error}")


if __name__ == "__main__":
    main()
