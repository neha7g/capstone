"""LiteLLM in-process gateway with Redis caching."""
import litellm

from . import cache


def complete(model: str, prompt: str, system: str | None = None) -> str:
    cache_key = f"{model}|{system}|{prompt}"
    if (hit := cache.get(cache_key)) is not None:
        return hit
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    out = litellm.completion(model=model, messages=msgs).choices[0].message.content
    cache.set(cache_key, out)
    return out
