"""Session storage backend.

If REDIS_URL is set, uses Redis (works across serverless instances).
Otherwise falls back to in-memory dict (single-process deployments).
"""

import json
import os
import time

_sessions = {}


class MemoryBackend:
    def get(self, code):
        return _sessions.get(code)

    def set(self, code, session):
        _sessions[code] = session

    def delete(self, code):
        _sessions.pop(code, None)

    def keys(self):
        return list(_sessions.keys())


class RedisBackend:
    def __init__(self, url):
        import redis
        self.r = redis.Redis.from_url(url, decode_responses=True)
        self.ttl = 24 * 600  # longest retention used by cleanup logic

    def get(self, code):
        raw = self.r.get(code)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, code, session):
        self.r.set(code, json.dumps(session), ex=self.ttl)

    def delete(self, code):
        self.r.delete(code)

    def keys(self):
        # skip cleanup scan when running on redis: TTL handles expiry
        return []


_url = os.environ.get("REDIS_URL")
backend = RedisBackend(_url) if _url else MemoryBackend()


def new_session():
    return {"offer": None, "answer": None, "created": time.time(), "servers": None}


def cleanup():
    """Evict expired in-memory sessions. No-op on redis (TTL handles it)."""
    for code in backend.keys():
        s = backend.get(code)
        if s is None:
            backend.delete(code)
            continue
        oa = s.get('offer') and s.get('answer')
        if (s.get('created') or 0) + 600 * (24 if oa else .5) < time.time():
            backend.delete(code)