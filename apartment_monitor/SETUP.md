# Modera Reynoldstown Apartment Monitor — macOS Setup

Monitors https://www.moderareynoldstown.com/atlanta/modera-reynoldstown/conventional/
twice daily and emails Omid.razmpour@emory.edu and dcginouves@gmail.com whenever
2-bed or 3-bed units on the 7th floor are listed (or to confirm none are listed).

Total setup time: ~10 minutes.

---

## Step 1 — Generate a Gmail App Password

You need a Gmail account with 2-Factor Authentication on. Gmail rejects regular
passwords for SMTP; you must use an "app password".

1. Open https://myaccount.google.com/security in a browser.
2. Under "How you sign in to Google", turn on **2-Step Verification** if it is
   not already on. Follow the prompts (phone number, verification code).
3. Go to https://myaccount.google.com/apppasswords.
4. In the "App name" field type `Apartment Monitor`, then click **Create**.
5. Google will show a 16-character password like `abcd efgh ijkl mnop`.
   **Copy it now** — you cannot view it again later.
6. You will paste this into `config.json` in Step 3.

---

## Step 2 — Install Python and dependencies

macOS already ships Python 3. From Terminal:

```bash
python3 --version            # confirm 3.9 or newer; install from python.org if missing
python3 -m pip install --upgrade pip
python3 -m pip install requests beautifulsoup4
```

That's it. The script only needs `requests` and `beautifulsoup4` — no Selenium
or Playwright required, because the Modera availability data is reachable via
plain HTTP.

---

## Step 3 — Create the project directory and files

From Terminal:

```bash
mkdir -p ~/apartment_monitor
cd ~/apartment_monitor
```

Copy the three files from this repo's `apartment_monitor/` folder into
`~/apartment_monitor/`:

- `apartment_monitor.py`
- `config.example.json`  →  rename a copy to `config.json`
- `state.json`

```bash
cp config.example.json config.json
open -e config.json     # opens in TextEdit
```

In `config.json`:

- Set `"gmail_email"` to the Gmail address that will *send* the emails.
- Set `"gmail_app_password"` to the 16-character password from Step 1
  (spaces are fine; the script accepts either form).
- Leave `"recipient_emails"` as-is — it already lists both target addresses.

Save the file. Then lock it down so others on the machine can't read your
password:

```bash
chmod 600 ~/apartment_monitor/config.json
```

---

## Step 4 — Schedule it with cron (9 AM and 5 PM Eastern)

cron is built into macOS. From Terminal:

```bash
which crontab            # confirms cron is installed (should print /usr/bin/crontab)
crontab -e               # opens your crontab in vi
```

Press `i` to enter insert mode, then paste these two lines:

```cron
0 9  * * * cd $HOME/apartment_monitor && TZ="America/New_York" /usr/bin/python3 apartment_monitor.py >> monitor.log 2>&1
0 17 * * * cd $HOME/apartment_monitor && TZ="America/New_York" /usr/bin/python3 apartment_monitor.py >> monitor.log 2>&1
```

Save and exit: press `Esc`, type `:wq`, press `Enter`.

Verify:

```bash
crontab -l               # should print the two lines you just added
```

> **Note on time zone:** macOS cron uses the system clock. The `TZ=` prefix
> ensures the script logs/timestamps in Eastern time, but the actual fire
> times (`0 9`, `0 17`) follow your Mac's clock. If your Mac is set to
> Eastern, you're done. If it's set to a different zone, change `0 9` and
> `0 17` to the equivalent local hours, OR change your Mac to Eastern in
> System Settings → General → Date & Time.

> **macOS permissions tip:** the first time cron runs, macOS may pop a
> "Terminal" or "cron" prompt asking for Full Disk Access. Grant it via
> System Settings → Privacy & Security → Full Disk Access, then add
> `/usr/sbin/cron`.

> **Laptop sleep:** cron does not wake a sleeping Mac. If your laptop is
> asleep at 9 AM, the run is skipped. Either leave the lid open / plugged
> in, or schedule a wake in System Settings → Battery → Schedule.

---

## Step 5 — Test it manually right now

```bash
cd ~/apartment_monitor
python3 apartment_monitor.py
```

You should see something like:

```
2026-05-14 18:42:01 [INFO] === Apartment monitor run starting ===
2026-05-14 18:42:02 [INFO] Fetched 14 units via API.
2026-05-14 18:42:02 [INFO] Filtered to 1 matching units (floor=7, bedrooms in [2, 3]).
2026-05-14 18:42:02 [INFO] Matching=1, previously_notified=0, new=1
2026-05-14 18:42:04 [INFO] Email sent to: Omid.razmpour@emory.edu, dcginouves@gmail.com
2026-05-14 18:42:04 [INFO] === Apartment monitor run complete ===
```

Check both inboxes (and Spam folders) for an email subject starting with
`[Modera Reynoldstown]`.

To inspect logs at any time:

```bash
tail -f ~/apartment_monitor/monitor.log
```

If the email did not arrive, jump to the troubleshooting guide.

---

## How it decides what to email

- Every run fetches the live availability list.
- It filters to **floor 7** units with **2 or 3 bedrooms**.
- It loads `state.json` to see which unit IDs were notified previously.
- The email always goes out (even when nothing matches), so you know the
  monitor is alive.
- After sending, it overwrites `state.json` with the *currently listed*
  matching units. A unit that disappears and later reappears will trigger
  a fresh notification.
