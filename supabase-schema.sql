-- NOTE: This SQL script must be run manually in the Supabase SQL Editor,
-- as changes in this repository will not apply automatically to the database.

create table if not exists send_logs (
  id bigint generated always as identity primary key,
  ip_address text,
  receiver text,
  file_name text,
  created_at timestamptz default now()
);

-- Atomic function to check rate limits (5 sends / 3 sec / IP),
-- check daily cap (400 sends / day UTC), and record the send log in a single transaction.
create or replace function check_and_log_send(
  p_ip text,
  p_receiver text,
  p_file_name text
) returns boolean
language plpgsql
security definer
as $$
declare
  v_recent_count integer;
  v_daily_count integer;
begin
  -- 1. Rate limit: max 5 requests per IP in a 3-second window
  select count(*)
  into v_recent_count
  from send_logs
  where ip_address = p_ip
    and created_at >= (now() - interval '3 seconds');

  if v_recent_count >= 5 then
    return false;
  end if;

  -- 2. Daily cap: stop at 400 sends per UTC day
  select count(*)
  into v_daily_count
  from send_logs
  where created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc';

  if v_daily_count >= 400 then
    return false;
  end if;

  -- 3. Atomic log insertion
  insert into send_logs (ip_address, receiver, file_name)
  values (p_ip, p_receiver, p_file_name);

  return true;
end;
$$;