# Run Commands

Run these from the repo root:

```bash
cd "/home/sonjoy/Bar tax/bangla-tax-rag"
mkdir -p .runtime
```

## 1. Start Backend In Background

Stable background run:

```bash
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4893 > .runtime/backend-4893.log 2>&1 & echo $! > .runtime/backend-4893.pid
```

Check backend health:

```bash
curl http://127.0.0.1:4893/health
```

Open the preferred same-origin frontend:

```text
http://127.0.0.1:4893/frontend/
```

Watch backend logs:

```bash
tail -f .runtime/backend-4893.log
```

## 2. Start Static Frontend In Background

Serve the static frontend on port `5173`:

```bash
nohup python3 -m http.server 5173 --directory frontend > .runtime/frontend-5173.log 2>&1 & echo $! > .runtime/frontend-5173.pid
```

Open in browser:

```text
http://127.0.0.1:5173
```

Use this only if you explicitly want the standalone static mode. The preferred wiring is the backend-served frontend at `http://127.0.0.1:4893/frontend/`.

Watch frontend server logs:

```bash
tail -f .runtime/frontend-5173.log
```

## 3. Run Frontend Smoke Test

This uses `frontend/config.local.json` or `RAG_BASE_URL` / `RAG_API_KEY`.

Foreground:

```bash
node frontend/smoke-test.mjs
```

Background:

```bash
nohup node frontend/smoke-test.mjs > .runtime/frontend-smoke.log 2>&1 & echo $! > .runtime/frontend-smoke.pid
```

Watch smoke-test output:

```bash
tail -f .runtime/frontend-smoke.log
```

## 4. Useful Checks

Backend OpenAPI:

```bash
curl http://127.0.0.1:4893/openapi.json
```

Inventory status:

```bash
curl http://127.0.0.1:4893/inventory/status
```

Frontend reachability:

```bash
curl -I http://127.0.0.1:5173
```

Backend-served frontend reachability:

```bash
curl -I http://127.0.0.1:4893/frontend/
curl http://127.0.0.1:4893/frontend/runtime-config.json
```

## 5. Stop Background Processes

Stop backend:

```bash
kill "$(cat .runtime/backend-4893.pid)"
```

Stop frontend:

```bash
kill "$(cat .runtime/frontend-5173.pid)"
```

Stop smoke test:

```bash
kill "$(cat .runtime/frontend-smoke.pid)"
```

## 6. One-Command Start For Both

```bash
bash -lc 'cd "/home/sonjoy/Bar tax/bangla-tax-rag"; mkdir -p .runtime; nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4893 > .runtime/backend-4893.log 2>&1 & echo $! > .runtime/backend-4893.pid; nohup python3 -m http.server 5173 --directory frontend > .runtime/frontend-5173.log 2>&1 & echo $! > .runtime/frontend-5173.pid'
```

## 7. One-Command Stop For Both

```bash
cd "/home/sonjoy/Bar tax/bangla-tax-rag" && kill "$(cat .runtime/backend-4893.pid)" "$(cat .runtime/frontend-5173.pid)"
```

## 8. Notes

- Backend default port in this repo is `4893`.
- Frontend default local port is `5173`.
- `frontend/config.local.json` currently points the frontend to a remote backend. If you want to test your local backend, change:

```json
{
  "apiBaseUrl": "http://127.0.0.1:4893"
}
```

- If the backend is protected, keep `apiKey` in `frontend/config.local.json`.
