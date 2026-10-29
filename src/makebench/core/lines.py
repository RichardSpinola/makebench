# SPDX-License-Identifier: MIT
"""JSON protocol lines between the app's processes, read without rescanning old bytes."""

# One message may carry a large table (about 50 bytes per row); the limit only stops a
# runaway process from filling the editor's memory.
MESSAGE_LIMIT = 64 * 1024 * 1024


class LineReader:
    """Split a byte stream into complete lines; each chunk is scanned once."""

    def __init__(self, limit=MESSAGE_LIMIT):
        self.limit = limit
        self.parts = []
        self.size = 0

    def feed(self, data):
        """Return the lines completed by `data`; ValueError when one passes the limit."""
        lines = []
        start = 0
        while True:
            end = data.find(b"\n", start)
            if end < 0:
                if start < len(data):
                    self.parts.append(data[start:])
                    self.size += len(data) - start
                if self.size > self.limit:
                    raise ValueError("line limit")
                return lines
            if self.size + end - start > self.limit:
                raise ValueError("line limit")
            self.parts.append(data[start:end])
            lines.append(b"".join(self.parts))
            self.parts, self.size = [], 0
            start = end + 1
