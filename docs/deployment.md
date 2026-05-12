# TooGraph Deployment

This document covers supported local deployment paths for running TooGraph outside the development loop. All paths keep the same application contract:

- Start command: `npm start`, which runs `node scripts/start.mjs`.
- Default public URL: `http://127.0.0.1:3477`.
- Health check: `http://127.0.0.1:3477/health`.
- Runtime data: `backend/data/`.
- Model configuration: the Model Providers page in the UI.

Do not configure model providers through startup environment variables. Start your local or private OpenAI-compatible gateway separately, then configure it in Model Providers and select the default text model there.

## Source Install

Use this path on a workstation or single server where Node.js and Python are already installed.

```bash
git clone https://github.com/OoABYSSoO/TooGraph.git
cd TooGraph
npm --prefix frontend install
python -m pip install -r backend/requirements.txt
npm start
```

To use a different port:

```bash
PORT=3999 npm start
```

To bind to another interface, set `TOOGRAPH_HOST`. This is mostly useful for containers or a LAN-only single-machine deployment.

```bash
TOOGRAPH_HOST=0.0.0.0 PORT=3477 npm start
```

If `TOOGRAPH_HOST=0.0.0.0`, the launcher still prints and checks the local URL through `127.0.0.1` unless `TOOGRAPH_PUBLIC_HOST` is set.

## Docker

Build the local image from the repository root:

```bash
docker build -t toograph:local .
```

Run with a named data volume:

```bash
docker run --rm \
  -p 3477:3477 \
  -v toograph-data:/app/backend/data \
  --name toograph \
  toograph:local
```

Then open:

```text
http://127.0.0.1:3477
```

The image sets:

```text
TOOGRAPH_HOST=0.0.0.0
PORT=3477
```

The container keeps persistent graphs, runs, settings, knowledge indexes, eval records, and local artifacts under `/app/backend/data`. Keep that path mounted as a Docker volume if you want data to survive container replacement.

To override the host port:

```bash
docker run --rm -p 3999:3477 -v toograph-data:/app/backend/data toograph:local
```

## Updates

For source installs:

```bash
git pull
npm --prefix frontend install
python -m pip install -r backend/requirements.txt
npm start
```

For Docker installs, rebuild the image and restart the container with the same data volume:

```bash
docker build -t toograph:local .
docker run --rm -p 3477:3477 -v toograph-data:/app/backend/data --name toograph toograph:local
```

## Operational Notes

- `npm start` releases occupied TooGraph ports before starting the server.
- `npm start` reuses `frontend/dist` when the build manifest matches the current frontend inputs.
- Use `TOOGRAPH_FORCE_FRONTEND_BUILD=1 npm start` only for source installs where frontend dependencies are present.
- Docker images are built with a ready `frontend/dist`; rebuild the image when frontend source changes.
- Do not commit `backend/data`, `buddy_home`, `.toograph_*`, `.dev_*`, generated `dist`, logs, or local credentials.
