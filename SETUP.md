# Naylor Newsletter Content System — Setup Guide

Complete these steps once. After setup, the system runs itself and editors manage their own newsletters.

---

## What you need (all free)

- A GitHub account (github.com)
- A Brevo account (brevo.com)
- Your Anthropic API key

---

## Step 1 — Create a GitHub account and repository

1. Go to **github.com** and sign up for a free account
2. Click **+** (top right) → **New repository**
3. Name it: `naylor-newsletter-system`
4. Set visibility to **Private**
5. Click **Create repository**

---

## Step 2 — Upload the project files

In your new repo, upload all files from the zip package:

1. Click **Add file** → **Upload files**
2. Drag in all files, keeping the folder structure:
   - `index.html` (root)
   - `newsletters.json` (root)
   - `.github/workflows/digest.yml`
   - `scraper/pipeline.py`
   - `scraper/config.py`
   - `scraper/web.py`
   - `scraper/summarize.py`
   - `scraper/email_brevo.py`
   - `scraper/__init__.py`
3. Click **Commit changes**

---

## Step 3 — Edit index.html with your repo details

In GitHub, open `index.html` and click the pencil (edit) icon. Find these two lines near the top of the `<script>` section and update them:

```javascript
const GITHUB_OWNER = "REPLACE_WITH_YOUR_GITHUB_USERNAME";
const GITHUB_REPO  = "REPLACE_WITH_YOUR_REPO_NAME";
```

Replace with your actual GitHub username and the repo name (`naylor-newsletter-system`).

Commit the change.

---

## Step 4 — Create a Brevo account and get your API key

1. Go to **brevo.com** and sign up for a free account
2. Verify your sender email address (Settings → Senders & IPs → Add a sender)
   - Use a Naylor email or any address you control
3. Get your API key: Settings → API Keys → Generate a new API key
4. Copy the key — you'll need it in Step 5

---

## Step 5 — Add secrets to GitHub

Secrets are encrypted — no one can see them after you add them.

In your GitHub repo: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these three secrets:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `BREVO_API_KEY` | Your Brevo API key from Step 4 |
| `BREVO_SENDER_EMAIL` | The sender email you verified in Brevo |

---

## Step 6 — Enable GitHub Pages (the editor portal)

1. In your repo: **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **root**
4. Click **Save**
5. After a minute, GitHub will show your portal URL:
   `https://YOUR-USERNAME.github.io/naylor-newsletter-system/`

Share this URL with editors. That's all they need.

---

## Step 7 — Create your own GitHub Personal Access Token (for saving changes)

Editors need a token to save newsletter changes through the portal. Each person creates their own.

1. Go to **github.com** → your profile → **Settings**
2. Scroll to **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
3. Click **Generate new token**
4. Name: `Newsletter portal`
5. Repository access: **Only select repositories** → choose `naylor-newsletter-system`
6. Permissions: **Contents** → **Read and write**
7. Click **Generate token** and copy it

Give this same set of instructions to each editor. They paste their token when prompted by the portal.

> **Note:** Tokens can be set to never expire — recommend this so editors aren't locked out.

---

## Step 8 — Test the system

1. Open the portal URL from Step 6
2. Enter your email and click **Look up**
3. Click **Add a newsletter** and add a test newsletter (use your own email as editor)
4. Go to your GitHub repo → **Actions** tab → **Newsletter Digest**
5. Click **Run workflow** → leave the newsletter name blank → **Run workflow**
6. Watch the run complete (takes 5–10 minutes)
7. Check your email for the digest

If it works: you're live. Share the portal URL with Carter and the content team.

---

## Running on a schedule

The workflow runs automatically every day at 6:00 AM UTC (2:00 AM ET). It checks which newsletters are due that day based on each editor's frequency setting, and runs only those.

To change the schedule, edit `.github/workflows/digest.yml` and update the cron line:
```yaml
- cron: "0 6 * * *"   # daily at 6am UTC
```

Common alternatives:
- `"0 6 * * 1"` — Mondays only
- `"0 6 * * 1,3"` — Mondays and Wednesdays

---

## Troubleshooting

**Portal shows an error loading config**
→ Check that `newsletters.json` is in the root of the repo and contains `{"newsletters": []}`

**GitHub Actions run fails**
→ Go to Actions tab, click the failed run, and read the error log. Most common causes:
  - Missing secret (check Step 5)
  - Brevo sender email not verified

**Editor gets a token error when saving**
→ Their token may have expired or have the wrong permissions. Have them create a new one (Step 7).

**Digest email arrives but no articles**
→ Some source sites block automated requests. Try different source URLs (category pages work better than homepages). The run log in GitHub Actions will show which sites were blocked.

---

## When IT is ready

When you're ready to move to Azure/M365 for a `@naylor.com` send address, the IT Deployment Guide (also in this package) has everything they need. The Python scraper code is identical — only the email and config storage modules change.

---

*Questions? Contact Alyssa Woods (awoods@naylor.com)*
