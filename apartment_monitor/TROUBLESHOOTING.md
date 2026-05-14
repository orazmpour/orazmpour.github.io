# Troubleshooting

## Email never arrived

1. **Check the spam/junk folder** of both Gmail and Emory mailboxes — Gmail
   often files first-time SMTP senders there.
2. **Re-check your app password.** The most common error. From the project
   directory:
   ```bash
   cat ~/apartment_monitor/config.json
   ```
   Confirm `gmail_app_password` is the 16-character string from
   https://myaccount.google.com/apppasswords (spaces are OK), **not** your
   regular Gmail password.
3. **Look at the log.** Errors like `SMTPAuthenticationError` mean the
   password is wrong; `Connection refused` means a network/firewall problem.
   ```bash
   tail -50 ~/apartment_monitor/monitor.log
   ```
4. **Generate a fresh app password** (the old one may have been revoked) at
   https://myaccount.google.com/apppasswords, paste into `config.json`, save,
   and re-run:
   ```bash
   python3 ~/apartment_monitor/apartment_monitor.py
   ```
5. **Verify the JSON is valid.** A stray comma will break the script.
   ```bash
   python3 -c "import json; json.load(open('$HOME/apartment_monitor/config.json'))"
   ```
   Silent output = valid. An exception = fix the indicated line.

## Script not running on schedule

1. **Confirm cron is registered:**
   ```bash
   crontab -l
   ```
   You should see two lines starting with `0 9` and `0 17`.
2. **Check the log right after the scheduled time.** If there is no entry at
   `09:00:xx`, cron didn't fire. Common causes:
   - Mac was asleep. cron does not wake the machine.
   - macOS hasn't granted cron Full Disk Access. Open
     System Settings → Privacy & Security → Full Disk Access, click `+`,
     press `Cmd+Shift+G`, type `/usr/sbin/cron`, add it, then re-test.
3. **Check the system mail spool** — cron writes failure output here:
   ```bash
   mail
   # press 'q' to exit
   ```
4. **Force a one-off run from cron's environment** to mimic what cron does:
   ```bash
   env -i HOME="$HOME" PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
     /bin/sh -c "cd $HOME/apartment_monitor && /usr/bin/python3 apartment_monitor.py"
   ```
   If this works but the cron entry doesn't, the issue is environmental
   (PATH, TZ, permissions) rather than the script itself.

## Modera website changed / no units returned

The script tries the JSON API first, then falls back to HTML scraping. If both
fail you'll see in the log:

```
Fetched 0 units via API.
Fetched 0 units via HTML scrape.
```

That run will still email "no new units available" so you're never left in
the dark. Next steps:

1. Open the listings URL in a browser and confirm units are shown there.
2. Open the Network tab in browser DevTools, refresh, and look for an XHR
   request that returns the unit list. Update `ENTRATA_AVAILABILITY_URL` (or
   the HTML selectors in `_fetch_via_html`) in `apartment_monitor.py` to
   match.
3. The fallback HTML parser also looks for `availability: [...]` JSON inside
   `<script>` tags, which catches most SPA rebuilds.

## Viewing logs

Live tail:
```bash
tail -f ~/apartment_monitor/monitor.log
```

Last 100 lines:
```bash
tail -100 ~/apartment_monitor/monitor.log
```

Search for errors:
```bash
grep -E "ERROR|WARN" ~/apartment_monitor/monitor.log
```

## Resetting state (force re-notification of all current units)

If you want the next run to treat every matching unit as new:
```bash
echo '{"notified_units": [], "last_run": null}' > ~/apartment_monitor/state.json
```

## Stopping the monitor

```bash
crontab -e         # delete the two lines, save with :wq
```
