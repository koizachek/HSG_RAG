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

    def __init__(self, allow_plain_text: bool = True) -> None:
        """
        Args:
            allow_plain_text: When False, suppress all non-JSON/preamble text
                and emit only a decoded top-level ``response`` field. Use this
                for structured-output agent streams where tool calls, tool
                arguments, or provider reasoning must never be shown to users.
        """
        self._buffer = ""
        self._mode: str | None = None   # None (undecided) | 'json' | 'plain'
        self._allow_plain_text = allow_plain_text
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
            self._mode = 'json' if stripped[0] == '{' or not self._allow_plain_text else 'plain'

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
        key_pos = self._find_top_level_response_key(buf)
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

    def _find_top_level_response_key(self, buf: str) -> int:
        """
        Return the position of a real top-level ``"response"`` object key.

        A simple ``str.find('"response"')`` is unsafe for streaming agent
        output: retrieval/tool arguments can contain the word "response" inside
        string values before the final structured answer arrives. Matching that
        text makes the UI stream internal query/database content. This scanner
        searches candidate JSON objects independently and only accepts keys at
        depth 1, outside strings, followed by a colon. Treating each object
        independently matters because agent streams can contain plain preamble,
        tool-call JSON, database snippets, and then the final structured object;
        braces or quotes in the earlier material must not poison the final
        answer scan.
        """
        start = 0
        while True:
            obj_start = buf.find('{', start)
            if obj_start == -1:
                return -1

            if not self._looks_like_json_object_start(buf, obj_start):
                start = obj_start + 1
                continue

            key_pos, obj_end, is_valid_candidate = self._scan_object_for_response_key(
                buf,
                obj_start,
            )
            if key_pos != -1:
                return key_pos
            if obj_end is not None:
                start = obj_end + 1
                continue
            if is_valid_candidate:
                return -1

            start = obj_start + 1

    @staticmethod
    def _looks_like_json_object_start(buf: str, obj_start: int) -> bool:
        i = obj_start + 1
        while i < len(buf) and buf[i] in ' \t\r\n':
            i += 1
        return i >= len(buf) or buf[i] in '"}'

    def _scan_object_for_response_key(
        self,
        buf: str,
        obj_start: int,
    ) -> tuple[int, int | None, bool]:
        """
        Scan one candidate JSON object.

        Returns:
            (key_position, object_end, is_valid_candidate)
            key_position is -1 when no top-level response key is present.
            object_end is None when the candidate object is still incomplete.
            is_valid_candidate is False for plain-text brace fragments that are
            not worth waiting on.
        """
        depth = 0
        in_string = False
        escaped = False
        expecting_key = False
        saw_key_or_end = False
        i = obj_start

        while i < len(buf):
            ch = buf[i]

            if in_string:
                if escaped:
                    escaped = False
                elif ch == '\\':
                    escaped = True
                elif ch == '"':
                    in_string = False
                i += 1
                continue

            if ch == '"':
                if depth == 1 and expecting_key and buf.startswith(self._FIELD_KEY, i):
                    end = i + len(self._FIELD_KEY)
                    j = end
                    while j < len(buf) and buf[j] in ' \t\r\n':
                        j += 1
                    if j < len(buf) and buf[j] == ':':
                        return i, None, True
                saw_key_or_end = True
                in_string = True
                i += 1
                continue

            if ch == '{':
                depth += 1
                expecting_key = depth == 1
            elif ch == '}':
                depth = max(0, depth - 1)
                if depth == 0:
                    return -1, i, True
                expecting_key = False
            elif ch == '[':
                depth += 1
                expecting_key = False
            elif ch == ']':
                depth = max(0, depth - 1)
                expecting_key = False
            elif depth == 1 and ch == ',':
                expecting_key = True
            elif depth == 1 and ch == ':':
                expecting_key = False

            i += 1

        return -1, None, saw_key_or_end or expecting_key
