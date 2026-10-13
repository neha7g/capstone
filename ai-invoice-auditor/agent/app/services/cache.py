"""Redis cache: llm:{sha256(prompt)} -> response, with TTL. Cache loss only makes things slower."""
import hashlib

import redis

from ..config import REDIS_URL

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
TTL = 60 * 60 * 24


def key(prompt: str) -> str:
    return "llm:" + hashlib.sha256(prompt.encode()).hexdigest()


def get(prompt: str):
    return r.get(key(prompt))


def set(prompt: str, value: str) -> None:
    r.setex(key(prompt), TTL, value)
