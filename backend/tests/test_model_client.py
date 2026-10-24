import httpx
import pytest

from app.model_client import ModelClient, ModelUnavailable


def make_client(handler):
    return ModelClient(
        base_url="http://127.0.0.1:11434",
        model="test-model",
        retry_delay_s=0,
        transport=httpx.MockTransport(handler),
    )


def test_generate_returns_text_and_sends_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"response": '{"sql": "SELECT 1"}'})

    out = make_client(handler).generate("hello")
    assert out == '{"sql": "SELECT 1"}'
    assert seen["url"] == "http://127.0.0.1:11434/api/generate"
    assert '"stream":false' in seen["body"].replace(" ", "")
    assert '"model":"test-model"' in seen["body"].replace(" ", "")


def test_retries_once_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"response": "ok"})

    assert make_client(handler).generate("hi") == "ok"
    assert calls["n"] == 2


def test_two_failures_raise_model_unavailable():  # T-015
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("offline")

    with pytest.raises(ModelUnavailable):
        make_client(handler).generate("hi")
    assert calls["n"] == 2  # exactly one retry, no more


def test_timeout_raises_model_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ModelUnavailable):
        make_client(handler).generate("hi")


def test_5xx_is_retried_then_fails():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ModelUnavailable):
        make_client(handler).generate("hi")
    assert calls["n"] == 2


def test_4xx_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(ModelUnavailable):
        make_client(handler).generate("hi")
    assert calls["n"] == 1


@pytest.mark.parametrize("body", [{"nope": 1}, {"response": 123}])
def test_malformed_body_raises(body):
    with pytest.raises(ModelUnavailable):
        make_client(lambda r: httpx.Response(200, json=body)).generate("hi")


def test_non_json_body_raises():
    with pytest.raises(ModelUnavailable):
        make_client(lambda r: httpx.Response(200, text="not json")).generate("hi")


@pytest.mark.parametrize("url", [
    "http://example.com:11434",
    "https://api.openai.com",
    "http://192.168.1.10:11434",
    "http://127.0.0.1.evil.com:11434",
])
def test_non_loopback_url_rejected(url):
    with pytest.raises(ValueError):
        ModelClient(base_url=url)


def test_is_available_true_and_false():
    assert make_client(lambda r: httpx.Response(200, json={"models": []})).is_available() is True

    def down(request):
        raise httpx.ConnectError("offline")

    assert make_client(down).is_available() is False