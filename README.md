ReviewPulse AI
Cross-Platform Product Review Intelligence with Grounded Search and Chat

DAMG 7245 — Big Data and Intelligent Analytics | Northeastern University | Spring 2026

Overview
ReviewPulse AI is a data-first analytics application that combines product review data from multiple sources, normalizes the data into one schema, enriches it with sentiment scores, creates semantic embeddings, and exposes a search and chat experience through an API and dashboard.

The current MVP is designed to demonstrate:

multi-source data ingestion

schema normalization across heterogeneous sources

Spark-based processing

sentiment enrichment

vector retrieval with ChromaDB

FastAPI endpoints for analytics, search, and grounded chat

Streamlit dashboard for end users

This project is intentionally data-heavy first and LLM-assisted second.

Current MVP
The current MVP includes:

Amazon sample review dataset ingestion

real Yelp Open Dataset ingestion

Reddit connector in demo/prototype mode

YouTube transcript sample ingestion

Python normalization pipeline for source profiling and early validation

PySpark normalization pipeline for unified parquet output

sentiment scoring pipeline over normalized reviews

embedding generation with sentence-transformers

ChromaDB vector index for semantic retrieval

FastAPI backend with /health, /stats/sources, /search/semantic, and /chat

Streamlit frontend with unified ask flow and analytics panel

Architecture
High-level flow:

Source data is collected from Amazon, Yelp, Reddit, and YouTube inputs

Source records are normalized into a shared schema

Spark writes a parquet-based normalized dataset

Sentiment scoring adds sentiment_label and sentiment_score

Embeddings are created for a balanced subset of review text

ChromaDB stores vectors and review metadata

FastAPI serves stats, semantic search, and grounded chat

Streamlit provides the user-facing dashboard

Data Sources
Source	Status in MVP	Notes
Amazon Reviews sample	Working	Current MVP uses sample/generated Amazon review content for testing the pipeline
Yelp Open Dataset	Working	Real Yelp review and business files are integrated in the normalization pipeline
Reddit API connector	Prototype	Connector exists; live API use depends on Reddit policy/approval and credentials
YouTube transcripts	Prototype/sample	Sample transcript-based records used in current MVP
Repository Structure
text
reviewpulse-ai/
├── poc/
│   ├── eda_amazon.py
│   ├── reddit_connector.py
│   ├── youtube_extractor.py
│   ├── normalize_schema.py
│   └── aspect_extraction.py
├── src/
│   ├── api/
│   │   └── main.py
│   ├── frontend/
│   │   └── app.py
│   ├── ml/
│   │   └── sentiment_scoring.py
│   ├── retrieval/
│   │   ├── build_embeddings.py
│   │   └── query_reviews.py
│   └── spark/
│       └── normalize_reviews_spark.py
├── dags/
│   └── dag_ingestion.py
├── tests/
│   └── test_normalization.py
├── data/
├── results/
├── .github/workflows/
├── pyproject.toml
├── poetry.lock
└── README.md
Tech Stack
Python 3.12

Poetry for dependency management

PySpark for distributed-style data processing

Pandas and matplotlib for exploratory analysis

sentence-transformers for embeddings

ChromaDB for vector storage and retrieval

FastAPI for backend APIs

Streamlit for the frontend dashboard

Anthropic SDK as optional LLM layer for grounded answer generation

GitHub Actions for CI

Setup
1. Install dependencies
bash
poetry install --no-root
2. Optional environment variables
bash
export ANTHROPIC_API_KEY="your_key_here"
export ANTHROPIC_MODEL="claude-3-sonnet-20240229"
If Anthropic is not configured or the model call fails, the chat endpoint falls back to a grounded extractive answer based on retrieved review text.

Run Order
Use this order for a clean end-to-end run.

Step 1: normalize raw/source data
bash
poetry run python poc/normalize_schema.py
Step 2: build Spark parquet output
bash
poetry run python src/spark/normalize_reviews_spark.py
Step 3: add sentiment scoring
bash
poetry run python src/ml/sentiment_scoring.py
Step 4: build embeddings and ChromaDB index
bash
poetry run python src/retrieval/build_embeddings.py
Step 5: run tests
bash
poetry run pytest tests/test_normalization.py -v
Step 6: start FastAPI
bash
poetry run uvicorn src.api.main:app --reload
Open:

http://127.0.0.1:8000/health

http://127.0.0.1:8000/docs

Step 7: start Streamlit
In another terminal:

bash
poetry run streamlit run src/frontend/app.py
API Endpoints
GET /health
Simple health check.

GET /stats/sources
Returns source counts and sentiment breakdown.

GET /search/semantic
Semantic search over embedded review text.

Parameters:

query

source_filter (optional)

n_results

GET /chat
Grounded answer generation using retrieved reviews.

Parameters:

query

source_filter (optional)

n_results

Response includes:

answer

citations

Frontend Features
The Streamlit dashboard currently includes:

unified ask flow for grounded Q&A

supporting retrieved review evidence

source-level metrics

source counts chart

sentiment breakdown chart

safer handling of sample Amazon URLs

Testing
The repository includes normalization-focused tests:

bash
poetry run pytest tests/test_normalization.py -v
Current tests validate:

Amazon normalization rules

Yelp normalization rules

Reddit normalization rules

YouTube normalization rules

unified schema contract

Current Limitations
This MVP works end to end, but there are known limitations:

Amazon review content in the current MVP is sample/generated rather than rich real product text

Amazon source URLs may not resolve to live product pages because the current dataset path uses sample data

Yelp business enrichment is used in the Python normalization path, while the Spark MVP path uses a simplified Yelp mapping for reliability

the sentiment pipeline is currently a lightweight baseline and tends to mark Amazon sample data as neutral

Reddit live API usage is not treated as a core dependency because Reddit access policies may require approval for some use cases

retrieval quality is structurally working, but still depends heavily on the quality of source text and metadata

Suggested Demo Flow
Use this order during demo:

show API health and overview metrics

show source counts and sentiment breakdown

ask a grounded question in the dashboard

show the returned answer

show citations and supporting retrieved reviews

explain how the answer is grounded in the vector search layer

Next Improvements
Good next improvements after MVP:

richer Amazon real-data ingestion

better sentiment model than the current rule-based baseline

stronger retrieval filtering and product-level matching

optional deployment to Streamlit Community Cloud and Cloud Run

better UI styling and layout polish

broader evaluation set for retrieval and answer quality

Team Roles
Suggested ownership split:

Data engineering: ingestion, normalization, Spark pipeline

ML/retrieval: sentiment scoring, embeddings, vector search, grounded answer layer

App layer: FastAPI, Streamlit, tests, documentation, demo preparation

Status
Current status: MVP complete and runnable locally.