# Local Sharing Guide: Exposing Ventro to Testers

This guide explains how to expose your locally running Ventro application (both the React frontend and FastAPI backend) to remote users over the internet using **ngrok**.

Because the application uses a split frontend/backend architecture, both services must be securely tunneled to the internet.

## Prerequisites

1. **ngrok:** A secure tunneling service. 
   - Install via Homebrew on macOS: `brew install -cask ngrok`
   - Sign up at [ngrok.com](https://ngrok.com/) to get your free auth token and authenticate your CLI if you haven't already (`ngrok config add-authtoken <your_token>`).
2. **Ventro Backend & Frontend:** Your local Docker Compose stack (`backend`, `frontend`, `postgres`, `redis`, `qdrant`, `ollama`, etc.) should be running.

---

## Step 1: Expose the Backend API

The remote users' frontend needs a public URL to send API requests to (login, document upload, matching, etc.).

1. Open a **new terminal window**.
2. Run the following command to tunnel the backend API (running on port 8000):
   ```bash
   ngrok http 8000
   ```
3. ngrok will display a status screen. Look for the **Forwarding** URL (e.g., `https://abc-123.ngrok-free.app`). 
4. **Copy this URL**. *(Leave this terminal running in the background).*

---

## Step 2: Configure the React Frontend

Right now, your React app is hardcoded (via `api.ts` and `.env`) to talk to `http://localhost:8000`. We need to tell the frontend to use the new public backend URL instead.

1. Open the `.env` file inside your `frontend` directory:
   ```bash
   nano frontend/.env
   ```
2. Add or update the `VITE_API_URL` variable with the URL you copied from Step 1:
   ```env
   VITE_API_URL=https://abc-123.ngrok-free.app
   ```
3. Because this is a build-time React environment variable, you must **rebuild** your frontend Docker container so it bakes the new URL into the JavaScript bundle:
   ```bash
   cd infra
   docker compose build frontend
   docker compose up -d frontend
   ```

*(Note: Whenever you restart ngrok on a free tier, your public URL will change, and you will need to repeat Step 2).*

---

## Step 3: Expose the Frontend UI

Now that the frontend is configured to talk to the public backend, you need to actually expose the frontend UI to your remote testers.

1. Open a **second new terminal window**.
2. Run the following command to tunnel the frontend (running on port 5173):
   ```bash
   ngrok http 5173
   ```
3. ngrok will display a status screen. Look for the second **Forwarding** URL (e.g., `https://xyz-987.ngrok-free.app`).

---

## Step 4: Share with Testers

1. Send the **Frontend Forwarding URL** (from Step 3) to your testers!
2. When they click the link, they will see the Ventro login screen.
3. When they interact with the app, their browser will seamlessly send API requests to your public **Backend Forwarding URL** (from Step 1), routing everything securely to your Macbook.

## Troubleshooting

- **CORS Errors / Network Failures on Login:** Ensure you actually rebuilt the frontend container (`docker compose build frontend`) after editing `.env`. If the React app is still trying to hit `localhost`, the remote user's browser will block it or fail to connect.
- **Connection Refused:** Ensure your backend and frontend Docker containers are actually up and running on your end (`docker compose up -d`).
- **Cannot create multiple tunnels:** If you are on a free ngrok tier, you may need a workaround to run multiple tunnels, or you can use `cloudflared` (Cloudflare Tunnels) which allows multiple free concurrent tunnels easily.
