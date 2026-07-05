"""Tests for the LLM interface: mark parsing and the (mocked) Ollama HTTP path."""

from unittest.mock import MagicMock

import pytest

from tools.llm_interface import LLMInterface

MARKS = ["++", "+", "N/A", "-", "--"]


# --------------------------------------------------------------------------- #
# _extract_mark — longest-first matching, token matching, no false positives
# --------------------------------------------------------------------------- #
class TestExtractMark:
    @staticmethod
    def extract(segment):
        ordered = sorted(MARKS, key=len, reverse=True)
        return LLMInterface._extract_mark(segment, ordered)

    @pytest.mark.parametrize(
        "segment,expected",
        [
            ("++ strong support", "++"),
            ("-- strong against", "--"),
            ("N/A not relevant", "N/A"),
            ("+ weak", "+"),
            ("- weak against", "-"),
            ("++", "++"),
        ],
    )
    def test_leading_mark(self, segment, expected):
        assert self.extract(segment) == expected

    def test_double_not_shadowed_by_single(self):
        # "++"/"--" must win over "+"/"-"
        assert self.extract("++") == "++"
        assert self.extract("--") == "--"

    def test_token_match_anywhere(self):
        assert self.extract("the answer is ++ here") == "++"

    def test_hyphenated_word_is_not_a_mark(self):
        # "well-known" must not be read as a "-" mark
        assert self.extract("this is well-known background") is None

    def test_none_when_absent(self):
        assert self.extract("no mark at all") is None


# --------------------------------------------------------------------------- #
# _parse_comparative — one mark per hypothesis line
# --------------------------------------------------------------------------- #
class TestParseComparative:
    HYPS = [{"id": "h1"}, {"id": "h2"}, {"id": "h3"}]

    def parse(self, text):
        return LLMInterface._parse_comparative(text, self.HYPS, MARKS)

    def test_well_formed(self):
        assert self.parse("h1: N/A\nh2: +\nh3: ++") == {"h1": "N/A", "h2": "+", "h3": "++"}

    def test_negatives_not_confused_with_separator(self):
        assert self.parse("h1: --\nh2: -\nh3: ++") == {"h1": "--", "h2": "-", "h3": "++"}

    def test_trailing_text_after_mark(self):
        assert self.parse("h1: + (weak)\nh2: N/A\nh3: - because x") == {
            "h1": "+", "h2": "N/A", "h3": "-",
        }

    def test_missing_hypothesis_defaults_na(self):
        assert self.parse("h1: ++") == {"h1": "++", "h2": "N/A", "h3": "N/A"}

    def test_garbage_all_na(self):
        assert self.parse("the model rambled with no marks") == {
            "h1": "N/A", "h2": "N/A", "h3": "N/A",
        }

    def test_empty(self):
        assert self.parse("") == {"h1": "N/A", "h2": "N/A", "h3": "N/A"}


# --------------------------------------------------------------------------- #
# generate / evaluate_hypotheses — mocked Ollama HTTP
# --------------------------------------------------------------------------- #
def _resp(payload):
    m = MagicMock()
    m.raise_for_status = lambda: None
    m.json = lambda: payload
    return m


@pytest.fixture
def llm(config, monkeypatch):
    """An LLMInterface whose connection check is stubbed out."""
    monkeypatch.setattr(
        "tools.llm_interface.requests.get", lambda *a, **k: _resp({"models": [{"name": "llama3.1"}]})
    )
    config.llm_model = "llama3.1"
    config.llm_context_window = 8192
    config.llm_max_tokens = 256
    return LLMInterface(config)


def test_generate_builds_payload_and_parses_response(llm, monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, **k):
        captured["url"] = url
        captured["json"] = json
        return _resp({"response": "  hello world  ", "done": True})

    monkeypatch.setattr("tools.llm_interface.requests.post", fake_post)

    out = llm.generate("a prompt", temperature=0.3, max_tokens=128)

    assert out == "hello world"  # stripped
    assert captured["url"].endswith("/api/generate")
    body = captured["json"]
    assert body["model"] == "llama3.1"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.3
    assert body["options"]["num_predict"] == 128
    assert body["options"]["num_ctx"] == 8192


def test_generate_raises_runtimeerror_on_http_failure(llm, monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr("tools.llm_interface.requests.post", boom)
    with pytest.raises(RuntimeError):
        llm.generate("x")


def test_evaluate_hypotheses_returns_mark_per_hypothesis(llm, hypotheses, monkeypatch):
    monkeypatch.setattr(
        llm, "generate", lambda *a, **k: "h1: N/A\nh2: ++\nh3: -"
    )
    result = llm.evaluate_hypotheses("article body", hypotheses, MARKS)
    assert result == {"h1": "N/A", "h2": "++", "h3": "-"}


def test_evaluate_hypotheses_defaults_all_na_on_failure(llm, hypotheses, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(llm, "generate", boom)
    result = llm.evaluate_hypotheses("article", hypotheses, MARKS)
    assert result == {"h1": "N/A", "h2": "N/A", "h3": "N/A"}


def test_evaluate_hypotheses_prompt_contains_full_article(llm, hypotheses, monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "generate", lambda prompt, **k: captured.setdefault("p", prompt) or "h1: +")
    big = "UNIQUE_MARKER " + ("body " * 5000)
    llm.evaluate_hypotheses(big, hypotheses, MARKS)
    assert "UNIQUE_MARKER" in captured["p"]
    assert len(captured["p"]) > 20000  # not truncated
