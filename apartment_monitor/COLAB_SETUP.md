# Run the Apartment Monitor on Google Colab — Beginner-Friendly Setup

You don't need to install anything on your computer. Everything runs in your browser.

**Total time:** about 10 minutes.

---

## Step 1 — Get a Gmail App Password (one-time, 2 minutes)

This is the *only* tricky part. Gmail won't let scripts send email with your normal password — you need a special 16-character "App Password" instead.

1. Open this link in a new browser tab: <https://myaccount.google.com/security>
2. Look for **"How you sign in to Google"** and turn on **2-Step Verification** if it isn't already on. (Follow the prompts — Google will text you a code.)
3. Open this link: <https://myaccount.google.com/apppasswords>
4. In the **App name** box, type `Apartment Monitor`. Click **Create**.
5. Google will show a 16-character password like `abcd efgh ijkl mnop`. **Copy it now** — it disappears as soon as you close the window.
6. Paste it into a notes app for the next step.

> If you don't see the App Passwords page, it's because 2-Step Verification isn't fully on yet. Finish that in Step 1.2 first.

---

## Step 2 — Open the notebook in Google Colab

1. Go to <https://colab.research.google.com/>. Sign in with your Google account.
2. In the top menu click **File → Upload notebook**.
3. Upload the file `apartment_monitor.ipynb` from this folder.
4. You'll see a page with several cells (gray code boxes and white text boxes).

> Alternative: if this notebook is on GitHub, you can also open it directly with:
> **File → Open notebook → GitHub → paste the repo URL**.

---

## Step 3 — Fill in your information (Cell 1)

Scroll to the cell labeled **"Cell 1 — CONFIG"**. You'll see three lines at the top:

```python
GMAIL_EMAIL        = "your.address@gmail.com"
GMAIL_APP_PASSWORD = "abcd efgh ijkl mnop"
RECIPIENTS         = [
    "Omid.razmpour@emory.edu",
    "dcginouves@gmail.com",
]
```

Replace:
- `your.address@gmail.com` → **your** Gmail address (this is the account that will *send* the emails).
- `abcd efgh ijkl mnop` → the 16-character App Password from Step 1. Keep the quotes around it.

The two recipient addresses are already set — leave them alone unless you want to change them.

When you're done editing, click the little **▶ Play button** on the left side of the cell. You should see:

```
Config looks good. From: your.address@gmail.com | To: ['Omid.razmpour@emory.edu', 'dcginouves@gmail.com']
```

---

## Step 4 — Connect Google Drive (Cell 2)

Click the **▶** on the next cell ("Cell 2 — Connect Google Drive").

A small window will pop up asking you to authorize access. Click **Connect to Google Drive**, pick your Google account, and click **Allow** on every screen.

This lets the notebook save a small file called `state.json` to your Drive so it remembers which units have already been emailed about. Without this, you might get duplicate notifications.

When it's done you'll see:

```
Drive connected. State will be saved at: /content/drive/MyDrive/apartment_monitor/state.json
```

---

## Step 5 — Run the check (Cell 3)

Click the **▶** on Cell 3. This is the cell that does the work:

1. Fetches the current Modera listings.
2. Filters to 7th-floor 2-bed and 3-bed units.
3. Compares against units it already emailed about.
4. Sends an email to both recipients (always — even if no matches).
5. Saves the state file.

You'll see log lines like:

```
=== Apartment monitor run starting ===
Fetched 12 units via API.
Total listings=12, matching (floor 7, [2, 3] bed)=1
Previously notified=0, new=1
Email sent to: Omid.razmpour@emory.edu, dcginouves@gmail.com
=== Run complete ===
```

**Within ~10 seconds, check both inboxes** (and the Spam folder — Gmail sometimes flags first-time sends). The subject will start with `[Modera Reynoldstown]`.

---

## Step 6 — How to get checks twice a day (read this carefully)

Colab does **not** automatically run notebooks on a schedule when the tab is closed. You have three options:

### Option A — Manual (simplest)
Bookmark the Colab page. Whenever you want a fresh check, open it and click **Runtime → Run all** at the top. Each run takes about 15 seconds.

You can do this twice a day yourself, or just whenever you remember.

### Option B — Auto-check while the browser tab is open
Run **Cell 4** at the bottom of the notebook. It'll wait until 9 AM Eastern (or 5 PM, whichever is next) and run the check automatically. Then wait until the next one. And so on.

**Limitations:**
- The Colab tab must stay open in your browser.
- Free Colab disconnects "idle" sessions after about 90 minutes. So Option B works best if you'll actually click around the tab during the day. Not reliable overnight.

To stop it: click **Runtime → Interrupt execution**.

### Option C — Truly automatic (advanced, set-it-and-forget-it)
For genuinely unattended checks (works even with your laptop closed) you need one of:

1. **Colab Pro** ($10/mo) — supports scheduled notebooks natively. Click **Runtime → Manage sessions → Schedule**.
2. **Google Apps Script** (free) — has built-in twice-a-day triggers, but you'd need to rewrite the script in JavaScript. Ask me and I can produce the Apps Script version for you.
3. **GitHub Actions** (free) — runs the original Python script on a schedule in the cloud. Also requires a bit more setup.

If you want any of these, just say "set me up with Option C-1" (or C-2 / C-3) and I'll walk you through it.

---

## Quick checklist

- [ ] Got Gmail App Password (16 characters)
- [ ] Uploaded `apartment_monitor.ipynb` to Colab
- [ ] Pasted email + App Password into Cell 1, ran it
- [ ] Ran Cell 2 and authorized Google Drive
- [ ] Ran Cell 3, saw "Email sent" in the log
- [ ] Confirmed email arrived at Omid.razmpour@emory.edu **and** dcginouves@gmail.com

If all six are checked, you're done. The monitor is working.

---

## Troubleshooting

**"Config looks good" never appears in Cell 1.**
You probably forgot to replace one of the placeholder values. Re-read Cell 1 — the lines that need changing have a `# ====== EDIT THESE THREE VALUES ======` comment right above them.

**Cell 3 ends with `SMTPAuthenticationError`.**
Your App Password is wrong, expired, or was revoked. Generate a fresh one at <https://myaccount.google.com/apppasswords>, paste it into Cell 1, re-run Cell 1, then re-run Cell 3.

**No email arrived but the log says "Email sent".**
Check the spam/junk folders of both recipients. Then check that the email addresses in `RECIPIENTS` are spelled exactly right.

**The log says "Fetched 0 units".**
The Modera site may have changed. You'll still get an email saying "No new units available" so you're not left in silence. If this keeps happening for several days, the script needs a small update — let me know and I'll fix it.

**I want to reset and get fresh notifications for all currently listed units.**
In Google Drive, open the folder `apartment_monitor/`, open `state.json`, replace its contents with `{"notified_units": [], "last_run": null}`, save, and re-run Cell 3.
