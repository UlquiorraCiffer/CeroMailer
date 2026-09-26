import os
import sys
import re
import mimetypes
import requests

# Same values as index.html — safe to keep here, this is the public/anon key,
# not a secret. The actual Gmail credentials never leave Vercel.
SUPABASE_URL = "https://euduprorskqxcvecapfo.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_gxIe1B6z1ZGKecBOksly4w_H9nw1xFq"
VERCEL_BASE_URL = "https://cero-mailer.vercel.app"
CREATE_SESSION_URL = f"{VERCEL_BASE_URL}/api/create-session"
SEND_API_URL = f"{VERCEL_BASE_URL}/api/send"

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def sanitize_filename(filename):
    return re.sub(r"[^a-zA-Z0-9._-]", "_", filename)


def create_session():
    response = requests.post(CREATE_SESSION_URL)
    if not response.ok:
        raise RuntimeError(f"{response.status_code}: {response.text}")
    data = response.json()
    return data["sessionId"]


def upload_file(session_id, file_path):
    file_name = sanitize_filename(os.path.basename(file_path))
    remote_path = f"sessions/{session_id}/{file_name}"

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


def send_email(session_id, receiver, subject, body):
    payload = {
        "sessionId": session_id,
        "receiver": receiver,
        "subject": subject,
        "body": body,
    }
    return requests.post(SEND_API_URL, json=payload)


def open_file_picker():
    """Open the native OS file-picker (multi-select). Returns a tuple of paths (possibly empty)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    selected = filedialog.askopenfilenames(
        title="Select files to attach",
        parent=root,
    )
    root.destroy()
    return selected


def main():
    print("=== Cero Mailer (CLI) ===")
    receiver = input("Receiver Gmail address: ").strip()
    subject = input("Subject: ").strip()
    body = input("Body: ").strip()

    print("\n  [1] Choose Files")
    print("  [Enter] Skip — send without attachments\n")
    choice = input(">> ").strip()

    if choice == "1":
        file_paths = open_file_picker()
    else:
        file_paths = ()

    # Validate each selected file
    for fp in file_paths:
        if not os.path.isfile(fp):
            print(f"File not found: {fp}")
            sys.exit(1)
        if os.path.getsize(fp) > MAX_FILE_SIZE:
            print(f"File too large (max 50MB): {fp}")
            sys.exit(1)

    # 1. Request server-issued session ID
    try:
        session_id = create_session()
    except Exception as e:
        print(f"Failed to create upload session: {e}")
        sys.exit(1)

    # 2. Upload each file under sessions/<sessionId>/...
    if file_paths:
        print(f"Uploading {len(file_paths)} file(s)...")
        for fp in file_paths:
            try:
                upload_file(session_id, fp)
            except Exception as e:
                print(f"Upload failed for {os.path.basename(fp)}: {e}")
                sys.exit(1)
    else:
        print("No files selected — sending without attachments.")

    # 3. Send email with sessionId
    print("Sending email...")
    response = send_email(session_id, receiver, subject, body)

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
