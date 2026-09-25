create table send_logs (
  id bigint generated always as identity primary key,
  ip_address text,
  receiver text,
  file_name text,
  created_at timestamptz default now()
);