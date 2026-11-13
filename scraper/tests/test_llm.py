import json
import types

import pytest
from conftest import REPO, report_payload

import config as cfgmod
import llm
from models import LLMReport


def cfg(provider="gemini", model="m1", fallback=None):
    data = {
        "sources": {"subreddits": ["stocks", "options"]},
        "llm": {"provider": provider, "model": model, "fallback_model": fallback},
    }
    return cfgmod.Config.model_validate(data)


# --- helpers ----------------------------------------------------------------- #

def test_strictify_forbids_extras_and_requires_everything():
    schema = llm.strictify(LLMReport.model_json_schema())

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    found = list(objects(schema))
    assert found
    for obj in found:
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])


def test_extract_json_handles_fences_and_prose():
    assert llm.extract_json('{"a": 1}') == {"a": 1}
    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.extract_json('Sure! Here you go: {"a": 1} Enjoy.') == {"a": 1}
    with pytest.raises(ValueError):
        llm.extract_json("no json here")


def test_api_key_is_never_shared_across_providers(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-legacy-key-value")
    assert llm.resolve_api_key("gemini") == "gemini-legacy-key-value"
    assert llm.resolve_api_key("openai") == ""
    assert llm.resolve_api_key("anthropic") == ""
    monkeypatch.setenv("LLM_API_KEY", "generic-key-value")
    assert llm.resolve_api_key("openai") == "generic-key-value"
    assert llm.resolve_api_key("gemini") == "generic-key-value"


def test_prompts_keep_untrusted_data_fenced_and_voice_rules():
    system = llm.SYSTEM_TEMPLATE.format(language="English")
    assert "UNTRUSTED" in system and "Never give investment advice" in system
    assert "never name people" in system
    assert "<raw_data>" in llm.USER_TEMPLATE


# --- orchestration -------------------------------------------------------------- #

def good_reply():
    return json.dumps(report_payload(count=8))


def test_analyze_uses_primary_model(monkeypatch):
    calls = []

    def adapter(key, model, system, user, schema, base_url):
        calls.append((key, model, base_url))
        return good_reply()

    monkeypatch.setitem(llm.ADAPTERS, "openai", adapter)
    report = llm.analyze("raw data", cfg("groq", "m1", "m2"), "secret-key-1234")
    assert calls == [("secret-key-1234", "m1", "https://api.groq.com/openai/v1")]
    assert len(report.top_tickers) == 8


def test_analyze_falls_back_to_second_model_and_trims(monkeypatch):
    seen = []

    def adapter(key, model, system, user, schema, base_url):
        seen.append(model)
        if model == "m1":
            raise RuntimeError("model gone api_key=abcdef0123456789abcdef0123456789abcdef01")
        return good_reply()

    monkeypatch.setitem(llm.ADAPTERS, "gemini", adapter)
    config = cfg("gemini", "m1", "m2")
    config.radar.top_n = 6
    report = llm.analyze("raw", config, "k" * 12)
    assert seen == ["m1", "m2"] and len(report.top_tickers) == 6


def test_analyze_rejects_invalid_model_output_and_raises_when_all_fail(monkeypatch, capsys):
    monkeypatch.setitem(llm.ADAPTERS, "gemini", lambda *a: json.dumps({"market_mood": {}, "top_tickers": []}))
    with pytest.raises(RuntimeError, match="All configured models failed"):
        llm.analyze("raw", cfg("gemini", "m1", "m2"), "k" * 12)
    assert "FAILED" in capsys.readouterr().out


# --- provider adapters against fakes ---------------------------------------------- #

def test_anthropic_adapter_uses_structured_output_and_handles_refusal(monkeypatch):
    import anthropic

    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            if captured.get("refuse"):
                pass
            return types.SimpleNamespace(
                stop_reason=captured.pop("_stop", "end_turn"),
                content=[types.SimpleNamespace(type="text", text='{"ok": true}')],
            )

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    schema = LLMReport.model_json_schema()
    assert llm._call_anthropic("key-value-1234", "claude-x", "SYS", "USER", schema, None) == '{"ok": true}'
    assert captured["model"] == "claude-x" and captured["system"] == "SYS"
    fmt = captured["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert "tool_choice" not in captured and "temperature" not in captured and "thinking" not in captured

    class RefusingMessages(FakeMessages):
        def create(self, **kwargs):
            return types.SimpleNamespace(stop_reason="refusal", content=[])

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: types.SimpleNamespace(messages=RefusingMessages()))
    with pytest.raises(RuntimeError, match="refusal"):
        llm._call_anthropic("key-value-1234", "claude-x", "SYS", "USER", schema, None)


def test_openai_compatible_adapter_falls_back_to_json_mode(monkeypatch):
    import httpx2
    import openai

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs["response_format"]["type"])
            if kwargs["response_format"]["type"] == "json_schema":
                response = httpx2.Response(400, request=httpx2.Request("POST", "https://x.example"))
                raise openai.BadRequestError("unsupported", response=response, body=None)
            message = types.SimpleNamespace(content='{"ok": true}')
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs["base_url"]))
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    out = llm._call_openai_compatible("key-value-1234", "some-model", "SYS", "USER", LLMReport.model_json_schema(), "https://api.groq.com/openai/v1")
    assert out == '{"ok": true}'
    assert calls == [("init", "https://api.groq.com/openai/v1"), "json_schema", "json_object"]


# --- retries ----------------------------------------------------------------------- #

class FakeServerError(Exception):
    code = 503


def test_transient_errors_are_retried_with_backoff(monkeypatch):
    sleeps, calls = [], []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)

    def adapter(key, model, system, user, schema, base_url):
        calls.append(model)
        if len(calls) < 3:
            raise FakeServerError("503 UNAVAILABLE high demand")
        return good_reply()

    monkeypatch.setitem(llm.ADAPTERS, "gemini", adapter)
    report = llm.analyze("raw", cfg("gemini", "m1", "m2"), "k" * 12)
    assert calls == ["m1", "m1", "m1"] and sleeps == list(llm.RETRY_DELAYS)
    assert len(report.top_tickers) == 8


def test_persistent_outage_tries_fallback_model_then_gives_up(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def adapter(key, model, system, user, schema, base_url):
        calls.append(model)
        raise FakeServerError("503")

    monkeypatch.setitem(llm.ADAPTERS, "gemini", adapter)
    with pytest.raises(RuntimeError):
        llm.analyze("raw", cfg("gemini", "m1", "m2"), "k" * 12)
    assert calls == ["m1"] * 3 + ["m2"] * 3


def test_permanent_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: pytest.fail("must not wait for a permanent error"))
    calls = []

    class Unauthorized(Exception):
        status_code = 401

    def adapter(key, model, system, user, schema, base_url):
        calls.append(model)
        raise Unauthorized("invalid api key")

    monkeypatch.setitem(llm.ADAPTERS, "gemini", adapter)
    with pytest.raises(RuntimeError):
        llm.analyze("raw", cfg("gemini", "m1", "m2"), "k" * 12)
    assert calls == ["m1", "m2"]


def test_invalid_output_gets_one_immediate_retry(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: pytest.fail("no wait for invalid output"))
    replies = iter(["not json at all", good_reply()])
    monkeypatch.setitem(llm.ADAPTERS, "gemini", lambda *a: next(replies))
    assert len(llm.analyze("raw", cfg("gemini", "m1"), "k" * 12).top_tickers) == 8
