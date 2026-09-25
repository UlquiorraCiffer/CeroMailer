# Gmail File-Sender — Micro Project Documentation

## 1. The Problem

At my institute, I often need to send practicals, quizzes, and other files
from an institute computer to my own Gmail. Doing this manually — opening
Gmail, composing a message, attaching the file, typing the address — every
single time is repetitive and slow. It gets worse because I don't always sit
at the same computer, and institute PCs are locked down: I can't install
large applications, and something like Windows Task Scheduler needs
technical access I don't usually have.

This project automates that: pick a file, type where it should go, and it's
sent — no manual composing, and nothing to install or configure each time.

## 2. Goals

- Send a file to a Gmail address programmatically, without composing an
  email by hand each time.
- Make it usable by anyone at the institute, not just me — no accounts, no
  logins, no setup on the machine it's run from.
- Don't depend on unreliable free storage or hosting.
- Support two ways of using it — a command-line version and a webpage
  version — and let the person choose.
- Eventually package it as a single install command, similar to how tools
  like Claude Code install with one line in PowerShell.

## 3. Tech Stack and What Each Piece Does

| Language / Tool | Role |
|---|---|
| **Python** | Core sending logic — connects to Gmail's SMTP server, builds the email, attaches files, detects file types automatically |
| **HTML/CSS + JS** | The webpage interface — a form to pick a file and type a receiving address |
| **Vercel** | Hosts the actual sending function as a small serverless API — this is where the Gmail credentials live, never on the user's machine |
| **Supabase** | Stores a log of each send (who, what file, when) and tracks rate-limit data |

PHP was part of the original plan but was dropped once the project moved to
a serverless architecture — more on why in Section 6.

## 4. How Sending Actually Works

Gmail won't accept a script logging in with a normal account password — it
requires an **App Password**, a 16-character code generated after turning on
2-Step Verification. This is used in place of a password specifically for
programs like this one.

Python's built-in `smtplib` library handles the connection to Gmail's SMTP
server (`smtp.gmail.com`, port `587`), logs in with the App Password, and
sends the message.

### The first working version (proof of concept)

```python
import smtplib
from email.message import EmailMessage

sender_email = "youraccount@gmail.com"
app_password = "your16charapppassword"
receiver_email = "youraccount@gmail.com"

msg = EmailMessage()
msg["Subject"] = "Test Email from Python"
msg["From"] = sender_email
msg["To"] = receiver_email
msg.set_content("Hello! This is a test email sent from my Python script.")

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(sender_email, app_password)
    server.send_message(msg)

print("Email sent successfully!")
```

This confirmed the core mechanism worked before adding any complexity on
top of it.

## 5. Build Progression

Each piece was built and tested individually before moving to the next,
rather than writing everything at once and hoping it worked.

### Step 1 — Hardcoded test email
Fixed sender, receiver, and message, just to prove the App Password +
`smtplib` connection worked at all.

### Step 2 — Accepting real input
Hardcoded values were replaced with `input()` prompts, so the script could
send to any address with any subject/body at runtime.

**Bug hit and fixed:** the line `msg.set_content= input("Body:")` used
assignment (`=`) instead of calling the method (`()`), which silently
overwrote `set_content` instead of invoking it — so the email body arrived
empty. The fix: `msg.set_content(input("Body:"))`. This turned into a useful
lesson: a name meant to *do* something needs `()`; a name meant to *hold*
something uses `=`.

### Step 3 — Attaching real files
The script was extended to attach an actual file, using Python's built-in
`mimetypes` library to detect the file type automatically (`.py`, `.html`,
`.php`, images, etc.), so the same code works for any file type without
hardcoding formats.

```python
import mimetypes

mime_type, _ = mimetypes.guess_type(file_path)
if mime_type is None:
    mime_type = "application/octet-stream"
main_type, sub_type = mime_type.split("/")

with open(file_path, "rb") as f:
    file_data = f.read()
    file_name = file_path.split("\\")[-1]

msg.add_attachment(file_data, maintype=main_type, subtype=sub_type, filename=file_name)
```

`"rb"` (read binary) mode is used so both text files and binary files
(images, PDFs) can be read the same way, without separate handling per type.

## 6. Architecture Decisions — What Changed and Why

The design went through several real revisions as practical constraints came
up. Documenting the *why* here, not just the final answer, because the
reasoning matters as much as the result.

**Considered:** hosting a PHP + Python backend on a free host (InfinityFree
or similar) for a web dashboard.
**Rejected:** free hosting has limited, unreliable storage — not something
to depend on for a tool meant to be used regularly.

**Considered:** a hosted "file-drop with a code" system — upload a file,
get a short code or QR, download it elsewhere with that code.
**Rejected:** still requires hosting and storage, so the same reliability
concern applies, even though the idea itself was reasonable.

**Considered:** using a third-party email API (EmailJS) to avoid dealing
with Gmail credentials at all.
**Decided against, in favor of something better:** rather than depending on
a third party's rate limits and sender identity, the project builds its own
equivalent — a small serverless function on **Vercel** holding a *spare*
Gmail account's App Password, with **Supabase** handling logging and
rate-limit tracking. This keeps full control, avoids third-party limits,
and the email still arrives clearly from a service address rather than a
generic relay.

**Considered:** using Supabase to also run the sending logic itself.
**Rejected:** Supabase's free tier auto-pauses a project after one week of
inactivity, requiring a manual restore from the dashboard. Since this tool
won't be used every single day (school breaks, gaps between practicals),
putting the *sending* function there would mean it silently stops working
during quiet periods. Vercel's serverless functions don't have this
pause behavior, so the split became: **Vercel runs the sending logic**
(must always work instantly), **Supabase only holds logs and rate-limit
data** (fine if it occasionally naps — the tool still works, just the log
has a gap until it's restored).

**Decided:** use a **separate, spare Gmail account** dedicated to this
service, rather than a personal one. This fully isolates any risk (spam
flags, rate-limit issues) from a personal inbox. Whatever account is used to
log in via `smtplib` is the address that shows up as the sender in the
recipient's inbox — Gmail doesn't allow spoofing a different "From" address
than the one authenticated.

**Decided against:** a temporary/disposable-email feature (generate a
throwaway inbox, auto-forward to a real Gmail). This idea was explored in
depth, but turned out to solve problems the architecture had already solved
another way — nobody ever types or logs into any Gmail credentials except
the one spare account living server-side, so there was no password step
left for disposable mail to remove. Dropped from scope entirely.

**Decided:** the tool needs to work identically across different institute
PCs without reinstalling anything each time. This ruled out PHP for the core
flow (PHP requires a running server to execute), in favor of:
- A **Python script**, eventually packaged into a single `.exe` (via
  PyInstaller) so no Python installation is needed on the machine running it.
- A **self-contained HTML page** for the webpage option.

**Planned:** a one-line PowerShell install command
(`irm <url> | iex`, the same style Claude Code's installer uses), served for
free via a GitHub repository's raw file — no hosting needed, since GitHub
just serves the file directly.

**Planned:** on install, both the CLI and webpage versions get installed
together. Every time the app is run afterward, it asks fresh — every time,
not just once — whether the user wants the command-line or webpage version.

## 7. Handling Abuse and Failure Cases

Since this is meant to be used by more than one person, on a service account
that could be misused, a few safeguards were planned in before building
further:

- **Rate limiting:** max 5 requests per IP address within a 3-second window.
  Beyond that, requests are rejected until the window resets. This is
  tracked in the Supabase logging table (timestamp per IP).
- **Why this matters more than it might seem:** a normal Gmail account can
  send roughly 500 emails a day before Google flags it for unusual activity.
  Without a rate limit, even a short burst of automated or accidental
  repeated requests could trip that limit and get the spare account
  temporarily suspended — the real worst-case outcome here, more than
  anything Vercel or Supabase would restrict on their own.
- **Input sanitization:** the receiver's email address and subject line are
  validated and stripped of newline characters before being placed into
  email headers, to prevent header injection (someone crafting input that
  smuggles in extra headers, like an unauthorized Bcc).
- **App Password never exposed:** stored only as an environment variable on
  Vercel — never in client-side code, never committed to the GitHub
  repository.
- **CORS restriction:** the API only accepts requests from the project's own
  frontend, not from arbitrary external websites trying to use it as a free
  relay.

## 8. Current Status

**Working and tested:**
- Core email sending via `smtplib` and a Gmail App Password
- User input for receiver, subject, and body
- File attachment with automatic MIME-type detection

**Designed, not yet built:**
- The Vercel `/api/send` serverless function (moving the working script
  server-side)
- The Supabase table for logs and rate-limit tracking
- The file picker (currently the file path is typed manually)
- The CLI menu (choose command-line vs. webpage each time the app runs)
- The standalone HTML page and its connection to the Vercel API
- Packaging into a `.exe` with PyInstaller
- The `install.ps1` PowerShell installer
- The public GitHub repository

## 9. What This Project Demonstrates

- Integrating with a real external service (Gmail SMTP) through a standard
  library
- Correctly distinguishing method calls from variable assignment, and
  debugging when the two get confused
- Automatic file-type detection instead of hardcoding formats
- Weighing real architecture trade-offs: hosted vs. serverless, storage
  reliability, third-party dependency vs. building it yourself, and
  planning for abuse before it happens rather than after
- Designing around an actual constraint (locked-down, shared institute PCs)
  instead of a textbook assignment with no real limitations
