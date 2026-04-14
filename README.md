# Real Estate SBLOC Simulator

Dashboard + API to evaluate funding a real estate down payment by:

- Selling equities (capital gains + opportunity cost), vs
- Borrowing via a Securities-Backed Line of Credit (SBLOC) (cashflow spread + margin call risk)

## Repo layout

- `frontend/`: Next.js + Tailwind dashboard UI
- `backend/`: FastAPI quantitative engine

## Local development

### Backend (FastAPI)

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
uvicorn app.main:app --reload --port 8000
```

Then visit `http://localhost:8000/docs`.

### Frontend (Next.js)

In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm run dev
```

Visit `http://localhost:3000`.

