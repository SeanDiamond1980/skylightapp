# Skylight Calendar Applet

Forward any event email → Claude parses it → adds to Google Calendar → syncs to Skylight.

---

## Deploy to Railway (recommended)

Railway is the easiest one-click deployment. Free tier included.

### Step 1 — Push to GitHub

Create a new GitHub repo and push this project to it:
```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_USER/skylight-applet.git
git push -u origin main
```

### Step 2 — Create Railway project

1. Go to https://railway.app and sign in (GitHub login works)
2. Click **New Project → Deploy from GitHub repo** and select your repo
3. Railway will auto-detect Python and start building

### Step 3 — Add a persistent volume for the database

1. In your Railway project, click **+ New → Volume**
2. Set the mount path to `/var/data`
3. In your service's **Variables** tab, add: `DATA_DIR` = `/var/data`

### Step 4 — Add environment variables

In your Railway service → **Variables** tab, add:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | From https://console.anthropic.com |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | `https://YOUR-RAILWAY-DOMAIN/auth/callback` |
| `DEFAULT_CALENDAR_ID` | `primary` |
| `POLL_INTERVAL_MINUTES` | `5` |

Railway gives you a public URL like `skylight-applet-production.up.railway.app` — use that for `GOOGLE_REDIRECT_URI`.

### Step 5 — Set up Google Calendar API

1. Go to https://console.cloud.google.com
2. Create a project → enable **Google Calendar API**
3. Go to **Credentials → Create → OAuth 2.0 Client ID** → Web application
4. Add your Railway URL as an **Authorized redirect URI**: `https://YOUR-RAILWAY-DOMAIN/auth/callback`
5. Copy Client ID and Secret into Railway variables

### Step 6 — Connect Google Calendar

Open your Railway URL → click **Setup → Sign in with Google** → authorize.

### Step 7 — Sync with Skylight

- In the Skylight app: **Settings → Calendar Sources → Add Google Calendar**
- Sign in with the same Google account
- Select your calendar → events appear on the frame within minutes

---

## Alternative: Deploy to Render

1. Go to https://render.com → **New → Web Service** → connect your GitHub repo
2. Render auto-reads `render.yaml` — just fill in the environment variables (same list as above)
3. The `render.yaml` already configures a 1 GB persistent disk at `/var/data`

---

## Local development

```bash
pip3 install -r requirements.txt
cp .env.example .env   # fill in values, use http://localhost:3000/auth/callback
python3 server.py
```
Open http://localhost:3000

---

## Adding events (three ways)

| Mode | How |
|---|---|
| **Manual** | Go to **Add Event**, paste any email text — Claude extracts the details |
| **Gmail Auto** | Label any email **"Skylight Events"** → auto-processed every 5 min |
| **Webhook** | Point Mailgun/Postmark/SendGrid inbound to `POST https://YOUR-DOMAIN/webhook/email` |

### Gmail auto-polling setup

Add these to your environment variables:
```
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_LABEL=Skylight Events
```
Get an App Password (not your real password) at https://myaccount.google.com/apppasswords

Create a Gmail label called **Skylight Events**, then label any event email to have it auto-processed.
