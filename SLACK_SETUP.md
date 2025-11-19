# Slack Integration Setup

Use this guide to connect your Slack workspace to the Agentic CEO Slack Events server.

## 1. Create a Slack App

1. Go to <https://api.slack.com/apps> and click **Create New App** → **From scratch**.
2. Name it (e.g., “Agentic CEO”) and pick your workspace.

## 2. Configure Basic App Settings

### a. OAuth & Permissions

1. Under **OAuth & Permissions**, add the scopes your bot needs. Recommended minimum:
   - `app_mentions:read`
   - `channels:history`
   - `chat:write`
   - `groups:history`
   - `im:history`
   - `mpim:history`
2. Click **Install App to Workspace** and authorize. Copy the **Bot User OAuth Token** (`xoxb-...`).

### b. Event Subscriptions

1. Enable **Event Subscriptions**.
2. For **Request URL**, you’ll need a public HTTPS endpoint (use `ngrok`/`cloudflared` during local dev). It must point to your FastAPI server:
   ```
   https://YOUR_TUNNEL_DOMAIN/slack/events
   ```
3. Once Slack verifies the URL, subscribe to events:
   - **Bot Events**: `message.channels`, `message.groups`, `message.im`, `message.mpim`, `app_mention`.
   - Add others as needed.

### c. Interactivity (optional)

If you want slash commands or interactive buttons, enable **Interactivity & Shortcuts** and set the same request URL (`/slack/events`) or dedicated endpoints.

### d. Socket Mode (optional)

If you prefer not to run a public endpoint, enable **Socket Mode** and use `slack_bolt`. This project currently expects the Events API via HTTPS, so only enable Socket Mode if you plan to adapt the server.

## 3. Gather Credentials

After configuring:

| Item                     | Where to find                                      | Env var              |
|--------------------------|----------------------------------------------------|----------------------|
| Signing Secret           | Basic Information → App Credentials                | `SLACK_SIGNING_SECRET` |
| Bot User OAuth Token     | OAuth & Permissions → Bot User OAuth Token         | `SLACK_BOT_TOKEN`      |
| (Optional) App-Level Token | Basic Information → App-Level Tokens             | `SLACK_APP_TOKEN`      |

## 4. Set Environment Variables

Add to your `.env` (or wherever your process loads secrets):

```
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=xoxb-...
# SLACK_APP_TOKEN=xapp-...   # only if using Socket Mode
```

Restart the FastAPI server after updating the `.env`.

## 5. Run the Slack Events Server

```
cd /Users/aichat/AgenticCEO
uvicorn slack_events_server:app --host 0.0.0.0 --port 8000 --reload
```

Use `ngrok http 8000` (or similar) to expose it, then paste the public URL into Slack’s Event Subscriptions.

## 6. Test the Integration

1. In Slack, mention the bot or send a message in a channel it’s in.
2. Watch the FastAPI logs for incoming events.
3. Your bot should reply with CEO decisions or delegate commands per the existing logic.

## 7. Troubleshooting

- **Request URL fails verification**: ensure the FastAPI server is reachable at the public URL and responds quickly.
- **Missing signature errors**: double-check `SLACK_SIGNING_SECRET`.
- **Bot not responding**: verify the bot is invited to the channel and has required scopes.
- **Ngrok/local tunnel down**: restart the tunnel and update the Slack request URL.

For more advanced workflows (slash commands, interactive buttons), extend `slack_events_server.py` with additional routes and register them in Slack’s app settings.

