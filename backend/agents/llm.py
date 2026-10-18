"""Gemini on Vertex AI: one helper that returns parsed JSON (and Search sources when grounding is on)."""
import json
import re
from functools import lru_cache

from config import GEMINI_LOCATION, GEMINI_MODEL, project_id


@lru_cache(maxsize=1)
def client():
    from google import genai
    return genai.Client(vertexai=True, project=project_id(), location=GEMINI_LOCATION)


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (handles ```json fences)."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("The model reply contained no JSON object")
    return json.loads(text[start:end + 1])


async def generate_json(parts, schema=None, temperature=0.2, search=False):
    """Call Gemini and return (data, sources).

    search=True turns on Grounding with Google Search. Gemini cannot combine Search with a
    forced JSON schema, so in that mode the prompt asks for JSON and we parse the text.
    """
    from google.genai import types

    config = {"temperature": temperature}
    if search:
        config["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    else:
        config["response_mime_type"] = "application/json"
        if schema is not None:
            config["response_schema"] = schema

    response = await client().aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(**config),
    )
    data = parse_json(response.text)
    return data, (_sources(response) if search else [])


def _sources(response) -> list[dict]:
    """The pages Google Search returned (grounding chunks), never URLs the model wrote."""
    sources, seen = [], set()
    try:
        for chunk in (response.candidates[0].grounding_metadata.grounding_chunks or []):
            web = getattr(chunk, "web", None)
            if web and web.uri and web.uri not in seen:
                seen.add(web.uri)
                sources.append({"title": web.title or web.uri, "url": web.uri})
    except Exception:
        pass  # sources are a bonus; never fail the agent over them
    return sources


async def search_pages(prompt: str, temperature=0.2) -> list[dict]:
    """Run a Google Search grounded prompt in plain text and return only the pages Search used.
    (Asking for JSON-only replies makes the model search less, so this one asks for prose.)"""
    from google.genai import types
    response = await client().aio.models.generate_content(
        model=GEMINI_MODEL, contents=[prompt],
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=temperature),
    )
    return _sources(response)
