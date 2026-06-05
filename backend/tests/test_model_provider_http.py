from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeStreamingResponse:
    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.iterated_lines = 0
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def iter_lines(self):
        for line in self.lines:
            self.iterated_lines += 1
            yield line


class CancellingStreamingResponse(FakeStreamingResponse):
    def __init__(self, token) -> None:
        super().__init__(['data: {"choices":[{"delta":{"content":"hello"}}]}'])
        self.token = token

    def iter_lines(self):
        self.iterated_lines += 1
        self.token.request("Stop during stream.")
        yield self.lines[0]


class RaisingAfterCloseStreamingResponse(FakeStreamingResponse):
    def __init__(self, token) -> None:
        super().__init__([])
        self.token = token

    def iter_lines(self):
        self.iterated_lines += 1
        self.token.request("Stop while stream is closing.")
        raise RuntimeError("stream was closed")


class FakeHttpxClient:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> "FakeHttpxClient":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def stream(self, *_args, **_kwargs) -> "FakeHttpxStreamResponse":
        return FakeHttpxStreamResponse()


class FakeHttpxStreamResponse:
    status_code = 200

    def __enter__(self) -> "FakeHttpxStreamResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def raise_for_status(self) -> None:
        return None


class ModelProviderHttpCancellationTests(unittest.TestCase):
    def test_stream_reader_raises_run_cancellation_before_consuming_more_tokens(self) -> None:
        from app.core.runtime.model_call_context import use_model_call_context
        from app.core.runtime.run_cancellation import RunCancellationRequested, RunCancellationToken
        from app.tools.model_provider_http import read_streaming_response_text

        response = FakeStreamingResponse(
            [
                'data: {"choices":[{"delta":{"content":"hello"}}]}',
                "",
            ]
        )
        token = RunCancellationToken("run_stream_cancel")
        token.request("Stop while streaming.")

        with use_model_call_context(cancellation_token=token):
            with self.assertRaises(RunCancellationRequested) as raised:
                read_streaming_response_text(response)

        self.assertEqual(str(raised.exception), "Stop while streaming.")
        self.assertEqual(response.iterated_lines, 0)
        self.assertTrue(response.closed)

    def test_stream_reader_closes_response_when_token_is_cancelled(self) -> None:
        from app.core.runtime.model_call_context import use_model_call_context
        from app.core.runtime.run_cancellation import RunCancellationRequested, RunCancellationToken
        from app.tools.model_provider_http import read_streaming_response_text

        token = RunCancellationToken("run_stream_cancel_mid_read")
        response = CancellingStreamingResponse(token)

        with use_model_call_context(cancellation_token=token):
            with self.assertRaises(RunCancellationRequested) as raised:
                read_streaming_response_text(response)

        self.assertEqual(str(raised.exception), "Stop during stream.")
        self.assertEqual(response.iterated_lines, 1)
        self.assertTrue(response.closed)

    def test_stream_reader_converts_closed_stream_error_after_cancellation(self) -> None:
        from app.core.runtime.model_call_context import use_model_call_context
        from app.core.runtime.run_cancellation import RunCancellationRequested, RunCancellationToken
        from app.tools.model_provider_http import read_streaming_response_text

        token = RunCancellationToken("run_stream_close_error")
        response = RaisingAfterCloseStreamingResponse(token)

        with use_model_call_context(cancellation_token=token):
            with self.assertRaises(RunCancellationRequested) as raised:
                read_streaming_response_text(response)

        self.assertEqual(str(raised.exception), "Stop while stream is closing.")
        self.assertEqual(response.iterated_lines, 1)
        self.assertTrue(response.closed)

    def test_streaming_fallback_does_not_retry_run_cancellation(self) -> None:
        from app.core.runtime.run_cancellation import RunCancellationRequested
        from app.tools.model_provider_http import post_streaming_json_with_fallback

        with patch("app.tools.model_provider_http.httpx.Client", FakeHttpxClient), patch(
            "app.tools.model_provider_http.read_streaming_response_text",
            side_effect=RunCancellationRequested("Stop during stream."),
        ), patch("app.tools.model_provider_http.request_json") as fallback_request:
            with self.assertRaises(RunCancellationRequested) as raised:
                post_streaming_json_with_fallback(
                    stream_url="http://127.0.0.1:1/v1/chat/completions",
                    fallback_url="http://127.0.0.1:1/v1/chat/completions",
                    timeout_sec=1,
                    stream_payload={"stream": True},
                    fallback_payload={"stream": False},
                    parse_stream=lambda _text: {},
                    error_label="chat request failed",
                )

        self.assertEqual(str(raised.exception), "Stop during stream.")
        fallback_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
