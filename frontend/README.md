# Hearthline frontend

Next.js 16 and React 19 frontend for the Hearthline real-estate planner.

## Local development

```bash
cp .env.example .env.local
npm ci
npm run dev
```

The local environment points browser requests at the FastAPI development server
on port 8000.

## Verification

```bash
npm run lint
npm run typecheck
npm run build
```

The production container uses Next.js standalone output and a relative API URL.
Caddy serves the frontend and FastAPI under one origin. Build, container,
configuration, and operations instructions live in the repository root
`README.md` and `docs/operations.md`.
