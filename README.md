# Industrial Digital Twin

This repository now contains:

- A React/Vite frontend in `industrial-digital-twin/`
- A Poetry-managed FastAPI backend in `backend_service/`
- Live source adapters for the proposal data sources:
  - SEC EDGAR
  - DOL OSHA
  - ITAC / DOE
  - EPA TRI
  - NASA POWER
  - FRED
  - EIA
  - SerpAPI market/news search
  - Glassdoor company search via RapidAPI
  - Stack Exchange
  - Reddit
  - Equipment catalog scraping targets
- A RAG chatbot pipeline that can retrieve from:
  - The project proposal PDF
  - The local codebase
  - Live source snapshots aggregated by the backend

## Environment Setup

Copy `.env.example` to `.env` at the repo root and fill in the API keys you actually have.

Important:

- `DOL_API_KEY`, `FRED_API_KEY`, and `EIA_API_KEY` are required for those live APIs.
- `NASA POWER` is integrated for site weather and solar context; it does not require a key, but `NASA_API_KEY` can still be stored for broader NASA Open API expansion.
- `SERPAPI_KEY` and `RAPIDAPI_KEY` enable the optional market/company feeds.
- `ANTHROPIC_API_KEY` is the primary chat provider; `OPENAI_API_KEY` and `GEMINI_API_KEY` are supported as fallback chat providers.
- `VOYAGE_API_KEY` and `PINECONE_API_KEY` are required for true vector retrieval.
- `PROPOSAL_PDF_PATH` is optional; if unset, the backend tries to auto-discover the proposal PDF in the repo or `~/Downloads`.
- Reddit needs OAuth credentials if you want authenticated access.
- SEC, EPA, ITAC, and the catalog scrapers do not require API keys, but they do use the configured URLs and user agent.

## Run The Backend With Poetry

```powershell
poetry install
poetry run uvicorn backend_service.main:app --reload --host 0.0.0.0 --port 8000
```

## Run The Frontend

```powershell
cd industrial-digital-twin
npm install
npm run dev
```

The frontend defaults to `http://localhost:8000` for the backend API.

## API Endpoints

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/sources`
- `POST /api/chat`
- `GET /api/rag/status`
- `POST /api/rag/reindex`

## Data Universe

The project is framed around a source universe of `45.5+ GB` across `7` real-world manufacturing data domains:

- SEC EDGAR filings: `~8 GB`
- OSHA inspections and accident records: `~12 GB`
- DOE IAC audits: `~2 GB`
- Equipment manufacturer catalogs and manuals: `~15 GB`
- FRED + EIA economic and energy indicators: `~500 MB`
- EPA TRI compliance records: `~5 GB`
- Engineering forums knowledge base: `~3 GB`

This is treated as a big-data integration challenge because each source uses a different acquisition strategy, schema, and refresh pattern. The running demo uses sampled live payloads for responsiveness, while the full-source architecture is designed around Spark for distributed processing and Airflow for orchestration.

## RAG Notes

- The first project-chat request may take longer because the backend may need to create or refresh the Pinecone index.
- RAG uses Voyage embeddings stored in Pinecone, then sends the retrieved proposal/code/source context to Anthropic by default, with OpenAI and Gemini available as model fallbacks when configured.
