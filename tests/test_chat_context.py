import asyncio
import unittest
from types import SimpleNamespace

from backend_service.chat import ProjectChatbot
from backend_service.models import ChatRequest, DashboardPayload, DatasetProfile


class DummyAggregator:
    def get_cached_dashboard(self):
        return None

    def build_placeholder_dashboard(self):
        raise NotImplementedError


def make_settings():
    return SimpleNamespace(
        anthropic_api_key=None,
        openai_api_key=None,
        gemini_api_key=None,
        anthropic_api_url="https://example.com/anthropic",
        openai_api_url="https://example.com/openai",
        gemini_api_url="https://example.com/gemini",
        anthropic_model="test-anthropic",
        normalized_openai_model="test-openai",
        normalized_gemini_model="test-gemini",
        anthropic_max_tokens=256,
        chat_history_turn_limit=4,
        chat_source_summary_limit=10,
        chat_rag_match_limit=4,
        chat_answer_cache_ttl_seconds=900,
        serpapi_key=None,
        rapidapi_key=None,
        market_research_ticker_list=[],
        glassdoor_query="manufacturing",
        rag_build_on_chat=False,
    )


def make_dashboard():
    return DashboardPayload(
        fetched_at="2026-04-03T16:00:00Z",
        stackStatus=[],
        liveFeed=[],
        proposalHighlights=["Live UI state should override static demo examples for current floor questions."],
        datasetProfile=DatasetProfile(
            total_estimated_size="1 GB",
            source_count=1,
            join_keys=["line_id"],
            engineering_note="Test payload",
            sources=[],
        ),
        sourceCards=[],
        sourceSnapshots=[],
    )


def make_request(workers):
    return ChatRequest(
        question="How can I improve overall staff utilization in Line B?",
        history=[],
        active_view="advisor",
        selected_line={
            "id": 2,
            "name": "Line B - Electronics",
            "stations": 3,
            "workers": workers,
            "machines": 6,
            "station_details": [
                {"label": "Robot Arm", "machines": 2, "workers": 2, "worker_to_machine_ratio": 1.0},
                {"label": "Assembly", "machines": 3, "workers": workers - 3, "worker_to_machine_ratio": round((workers - 3) / 3, 2)},
                {"label": "QC Station", "machines": 1, "workers": 1, "worker_to_machine_ratio": 1.0},
            ],
        },
        factory_state={
            "source": "live_client_ui",
            "totals": {"lines": 3, "stations": 10, "workers": 30, "machines": 18},
            "focused_line_name": "Line B - Electronics",
            "lines": [
                {
                    "id": 2,
                    "name": "Line B - Electronics",
                    "stations": 3,
                    "workers": workers,
                    "machines": 6,
                }
            ],
        },
    )


class ChatContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chatbot = ProjectChatbot(make_settings(), DummyAggregator(), rag_service=None)
        cls.dashboard = make_dashboard()

    @classmethod
    def tearDownClass(cls):
        asyncio.run(cls.chatbot._anthropic_client.aclose())

    def test_prompt_includes_authoritative_live_factory_state(self):
        request = make_request(9)
        prompt = self.chatbot._build_prompt(
            request,
            self.dashboard,
            [
                {
                    "citation": "industrial-digital-twin/src/data/demoData.js",
                    "source_type": "code",
                    "text": "Bundled demo example for Line B.",
                }
            ],
            "RAG is ready.",
            [],
        )

        self.assertIn("CURRENT FOCUSED LINE FACTS", prompt)
        self.assertIn("AUTHORITATIVE LIVE CLIENT FACTORY STATE", prompt)
        self.assertIn('"workers": 9', prompt)
        self.assertIn('"stations": 3', prompt)
        self.assertIn("do not let it override the live client UI factory state", prompt)

    def test_cache_key_changes_when_factory_state_changes(self):
        first_key = self.chatbot._build_cache_key(make_request(9), self.dashboard)
        second_key = self.chatbot._build_cache_key(make_request(12), self.dashboard)

        self.assertNotEqual(first_key, second_key)

    def test_citations_include_live_client_ui_state(self):
        citations = self.chatbot._build_citations(make_request(9), self.dashboard, [], [])

        self.assertIn("Live client UI factory state", citations)


if __name__ == "__main__":
    unittest.main()
