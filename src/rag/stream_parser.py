"""
Incremental extraction of the user-visible answer from a streamed model output.

Why this exists (latency fix / streaming):
The lead agent uses provider-native structured output, so the final model call
streams JSON tokens like:

    {"response": "Der EMBA HSG kostet ...", "additional_details": ...}

Streaming that raw JSON to the user is unacceptable. This parser consumes the
token stream incrementally and emits ONLY the decoded value of the "response"
field as it grows. If the stream turns out not to be JSON (plain text models,
fallback models without structured output), it passes text through unchanged.
"""


class ResponseFieldStreamParser:
    """Feed streamed text chunks, receive displayable deltas back."""

    _ESCAPES = {
        'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
        '"': '"', '\\': '\\', '/': '/',
    }
    _FIELD_KEY = '"response"'

    def __init__(self) -> None:
        self._buffer = ""
        self._mode: str | None = None   # None (undecided) | 'json' | 'plain'
        self._emitted_plain = 0
        self._emitted_value = 0
        self.field_complete = False

    def feed(self, text: str) -> str:
        """Add a stream chunk; returns the new displayable delta ('' if none)."""
        if not text:
            return ""
        self._buffer += text

        if self._mode is None:
            stripped = self._buffer.lstrip()
            if not stripped:
                return ""
            self._mode = 'json' if stripped[0] == '{' else 'plain'

        if self._mode == 'plain':
            delta = self._buffer[self._emitted_plain:]
            self._emitted_plain = len(self._buffer)
            return delta

        if self.field_complete:
            return ""

        value, closed = self._extract_response_value()
        if value is None:
            return ""
        delta = value[self._emitted_value:]
        self._emitted_value = len(value)
        if closed:
            self.field_complete = True
        return delta

    # ------------------------------------------------------------------ #

    def _extract_response_value(self) -> tuple[str | None, bool]:
        """
        Scan the buffer for the "response" field and decode its (possibly
        still growing) string value. Returns (value_so_far, is_closed).
        (None, False) when the field has not started yet.
        """
        buf = self._buffer
        key_pos = buf.find(self._FIELD_KEY)
        if key_pos == -1:
            return None, False

        colon = buf.find(':', key_pos + len(self._FIELD_KEY))
        if colon == -1:
            return None, False

        i = colon + 1
        while i < len(buf) and buf[i] in ' \t\r\n':
            i += 1
        if i >= len(buf) or buf[i] != '"':
            # Value did not start (yet) or is not a string — emit nothing.
            return None, False
        i += 1

        out: list[str] = []
        while i < len(buf):
            ch = buf[i]
            if ch == '\\':
                if i + 1 >= len(buf):
                    break  # incomplete escape — wait for more input
                nxt = buf[i + 1]
                if nxt == 'u':
                    if i + 6 > len(buf):
                        break  # incomplete \uXXXX — wait for more input
                    try:
                        out.append(chr(int(buf[i + 2:i + 6], 16)))
                    except ValueError:
                        out.append(buf[i:i + 6])
                    i += 6
                else:
                    out.append(self._ESCAPES.get(nxt, nxt))
                    i += 2
            elif ch == '"':
                return ''.join(out), True
            else:
                out.append(ch)
                i += 1

        return ''.join(out), False
