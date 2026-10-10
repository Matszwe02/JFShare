<div align="center">

<img src="favicon.svg" alt="JFShare" width="110">

# JFShare

**Just File Share** — share files with no size limit, unlimited bandwidth, no sign-in, fully peer-to-peer.

Files travel directly between browsers over WebRTC. The optional backend only pairs devices — it never sees your data.

![license](https://img.shields.io/badge/license-GPL--2.0-blue)
![webRTC](https://img.shields.io/badge/transport-WebRTC-brightgreen)
![backend](https://img.shields.io/badge/backend-optional-lightgrey)
![sign-up](https://img.shields.io/badge/sign--up-none-success)

**Try it** → [jfshare.vercel.app](https://jfshare.vercel.app) · [matszwe02.github.io/JFShare](https://matszwe02.github.io/JFShare)

</div>

---

## Official instances

- ### [https://jfshare.vercel.app](https://jfshare.vercel.app)

- ### [https://matszwe02.github.io/JFShare](https://matszwe02.github.io/JFShare)


## Features

- **No size limit** — send terabyte-sized files
- **No registration** — open the site and start sharing
- **Bi-directional** — once connected, both peers can send and receive at will
- **Directory transfer** — drag & drop whole folders (supported browsers)
- **Mount mode** — share a local directory and let the other side browse it like a file manager, with per-file or whole-folder (ZIP) downloads
- **Resilient connections** — 4-stage negotiation fallback (direct → reversed roles → TURN relay), automatic reconnection, and live speed / ETA display
- **Backend optional** — works with the hosted signaling server, your own instance, or pure manual code exchange with no server at all
- **Signed exchanges** — reconnection payloads are verified with ECDSA signatures to prevent session hijacking

## How it works

1. The host opens the site and gets a link + QR code pointing at a one-word session code.
2. The peer opens the link; both browsers exchange WebRTC offers/answers through the signaling server.
3. If a direct connection fails, the roles reverse; if that fails too, traffic is relayed through a Cloudflare TURN server.
4. Once the data channel opens, files stream directly between the two machines.

**The catch:** you are the server. Files are only available while you keep the connection open — there is no upload-and-download-later storage. The backend just pairs devices.

## Self-hosting

Requirements: Python 3.10+.

```bash
git clone https://github.com/matszwe02/JFShare.git
cd JFShare
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

Then open `http://localhost:8000` — the app and API are served from the same origin. (Set `CONFIG.API_URL` in `index.html` if you host the frontend separately.)

### Configuration

The server runs with zero configuration. All environment variables are optional:

| Variable | Purpose |
| --- | --- |
| `REDIS_URL` | Use Redis for session storage instead of an in-memory dict. Recommended for serverless/multi-instance deployments (e.g. Vercel), where TTL handles expiry. |
| `TURN_KEY_ID` | Cloudflare TURN key ID used to mint ICE credentials. |
| `TURN_KEY_API_TOKEN` | Cloudflare TURN key API token. |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token used to query TURN usage. |
| `ACCOUNT_ID` | Cloudflare account ID for the usage query. |

Without TURN credentials, the app falls back to public Google STUN servers.

### TURN usage guard

`cf.py` protects your Cloudflare free tier: before minting credentials it checks the last 31 days of TURN egress against the 1,000 GB monthly allowance and refuses to issue new credentials once usage reaches the configured percentage. While credentials are live, a background thread keeps polling usage and revokes them immediately if the threshold is crossed.

### API

| Endpoint | Description |
| --- | --- |
| `POST /offer` | Create a session, returns `{ "code": "..." }` |
| `GET /offer/{code}` | Fetch a session's offer/answer state |
| `PATCH /offer/{code}` | Update `offer` or `answer` for a session |
| `GET /turn/{code}` | Get TURN ICE servers for a session |

Sessions expire on their own: 30 minutes after creation, or 12 hours once both offer and answer are present (Redis: 4-hour TTL).

## About

This project was **vibe-coded** — built iteratively with an AI assistant, commit by commit, rather than written top-down. It's released under GPL-2.0, so fork it, break it, ship it.

## License

GNU General Public License v2.0 — see [LICENSE](LICENSE).
