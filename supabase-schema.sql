-- Run this in Supabase: Dashboard > SQL Editor > New query > Run

create table send_logs (
  id bigint generated always as identity primary key,
  ip_address text,
  receiver text,
  file_name text,
  created_at timestamptz default now()
);

-- Note: the "uploads" storage bucket itself is created from the
-- Storage tab in the dashboard, not from SQL. See setup steps in chat.
