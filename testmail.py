import smtplib
import mimetypes
from email.message import EmailMessage

sender_email = input("Your Gmail: ")
app_password = input("App password: ")
receiver_email = input("Receiver Gmail: ")
file_path = input("Full path of file to attach: ")

msg = EmailMessage()
msg["Subject"] = input("Subject: ")
msg["From"] = sender_email
msg["To"] = receiver_email
msg.set_content(input("Body: "))

# --- Attach the file ---
mime_type, _ = mimetypes.guess_type(file_path)   # e.g. "image/png", "text/x-python"
if mime_type is None:
    mime_type = "application/octet-stream"        # fallback for unknown types#for ex-"This is some kind of file. Treat it as generic data."
main_type, sub_type = mime_type.split("/")

with open(file_path, "rb") as f:
    file_data = f.read()
    file_name = file_path.split("\\")[-1]          # just the filename, not full path 
msg.add_attachment(file_data, maintype=main_type, subtype=sub_type, filename=file_name)

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(sender_email, app_password)
    server.send_message(msg)

print("Email sent with attachment!")