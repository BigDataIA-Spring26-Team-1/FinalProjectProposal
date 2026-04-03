from __future__ import annotations

from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str, separator: str = ",") -> list[str]:
    return [item.strip() for item in value.split(separator) if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Industrial Digital Twin API"
    app_env: str = "development"
    dashboard_cache_ttl_seconds: int = 900
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    sec_user_agent: str = "IndustrialDigitalTwin/0.1 (student project; contact your-email@example.com)"
    sec_tickers: str = "CAT,DE,GE,HON"
    market_research_tickers: str = "NVDA,AMD,AVGO,MU,TSM,QCOM,ASML,AMAT,LRCX,KLAC,INTC"

    dol_api_key: str | None = None
    dol_inspection_url: str = "https://data.dol.gov/get/inspection"
    osha_limit: int = 8
    osha_public_citedstandards_url: str = "https://www.osha.gov/ords/imis/citedstandard.naics"
    osha_naics_codes: str = "31,32,33"
    osha_public_state_scope: str = "FEFed"

    itac_download_page_url: str = "https://itac.university/download"
    itac_zip_url: str = "https://itac.university/storage/ITAC_Database.zip"
    itac_sample_rows: int = 5

    nasa_api_key: str | None = None
    nasa_site_name: str = "Boston Plant"
    nasa_latitude: float = 42.3601
    nasa_longitude: float = -71.0589
    nasa_power_daily_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    nasa_power_community: str = "SB"
    nasa_power_parameters: str = "ALLSKY_SFC_SW_DWN,T2M_MAX,T2M_MIN,RH2M,WS10M"
    nasa_lookback_days: int = 7

    anthropic_api_key: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_api_key: str | None = None
    openai_api_url: str = "https://api.openai.com/v1/chat/completions"
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    gemini_model: str = "gemini-2.5-flash"
    anthropic_max_tokens: int = 700
    chat_history_turn_limit: int = 4
    chat_source_summary_limit: int = 10
    chat_rag_match_limit: int = 4
    chat_answer_cache_ttl_seconds: int = 900

    voyage_api_key: str | None = None
    voyage_api_url: str = "https://api.voyageai.com/v1/embeddings"
    voyage_model: str = "voyage-4-lite"
    voyage_output_dimension: int = 1024
    voyage_batch_size: int = 4
    voyage_retry_attempts: int = 8
    voyage_retry_base_seconds: float = 10.0
    voyage_inter_batch_delay_seconds: float = 4.0

    pinecone_api_key: str | None = None
    pinecone_control_api_url: str = "https://api.pinecone.io"
    pinecone_api_version: str = "2025-10"
    pinecone_index_name: str = "industrial-digital-twin-rag"
    pinecone_metric: str = "cosine"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    proposal_pdf_path: str | None = None
    rag_namespace_prefix: str = "industrial-digital-twin"
    rag_build_on_chat: bool = False
    rag_top_k: int = 6
    rag_chunk_chars: int = 1200
    rag_chunk_overlap_chars: int = 160
    rag_code_lines_per_chunk: int = 80
    rag_code_overlap_lines: int = 12
    rag_max_snippet_chars: int = 950

    fred_api_key: str | None = None
    fred_series_ids: str = "IPMAN,PCU333333"
    fred_observation_limit: int = 3

    eia_api_key: str | None = None
    eia_state_id: str = "US"
    eia_length: int = 6
    eia_retail_sales_url: str = "https://api.eia.gov/v2/electricity/retail-sales/data/"

    epa_state_abbr: str = "MA"
    epa_tri_limit: int = 6
    epa_tri_url_template: str = (
        "https://enviro.epa.gov/enviro/efservice/tri_facility/state_abbr/{state}/JSON/rows/0:{end}"
    )

    stackexchange_key: str | None = None
    stackexchange_site: str = "engineering"
    stackexchange_query: str = "predictive maintenance"
    stackexchange_tags: str = ""
    stackexchange_pagesize: int = 5

    serpapi_key: str | None = None
    serpapi_url: str = "https://serpapi.com/search.json"
    serpapi_engine: str = "google_news"
    serpapi_query: str = "semiconductor manufacturing outlook"
    serpapi_limit: int = 5
    chat_market_research_limit: int = 6

    rapidapi_key: str | None = None
    glassdoor_rapidapi_host: str = "glassdoor-real-time.p.rapidapi.com"
    glassdoor_company_search_path: str = "/companies/search"
    glassdoor_reviews_path: str = "/companies/reviews"
    glassdoor_query: str = "semiconductor"
    glassdoor_limit: int = 4

    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_username: str | None = None
    reddit_password: str | None = None
    reddit_user_agent: str = "industrial-digital-twin/0.1 by student-project"
    reddit_subreddits: str = "manufacturing,PLC,engineering"
    reddit_limit: int = 5

    grainger_search_url: str = "https://www.grainger.com/category/material-handling"
    fanuc_search_url: str = "https://www.fanucamerica.com/products/robots"
    abb_search_url: str = "https://new.abb.com/products/robotics"

    frontend_api_base_url: str = "http://localhost:8000"

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @cached_property
    def sec_ticker_list(self) -> list[str]:
        return [ticker.upper() for ticker in _split_csv(self.sec_tickers)]

    @cached_property
    def fred_series_list(self) -> list[str]:
        return [series.upper() for series in _split_csv(self.fred_series_ids)]

    @cached_property
    def osha_naics_list(self) -> list[str]:
        return _split_csv(self.osha_naics_codes)

    @cached_property
    def market_research_ticker_list(self) -> list[str]:
        return [ticker.upper() for ticker in _split_csv(self.market_research_tickers)]

    @cached_property
    def nasa_power_parameter_list(self) -> list[str]:
        return [parameter.upper() for parameter in _split_csv(self.nasa_power_parameters)]

    @cached_property
    def normalized_openai_model(self) -> str:
        return self.openai_model.removeprefix("openai/")

    @cached_property
    def normalized_gemini_model(self) -> str:
        return self.gemini_model.removeprefix("gemini/")

    @cached_property
    def stackexchange_tag_list(self) -> list[str]:
        return _split_csv(self.stackexchange_tags, separator=";")

    @cached_property
    def subreddit_list(self) -> list[str]:
        return _split_csv(self.reddit_subreddits)

    @cached_property
    def catalog_targets(self) -> dict[str, str]:
        return {
            "Grainger": self.grainger_search_url,
            "FANUC": self.fanuc_search_url,
            "ABB": self.abb_search_url,
        }
