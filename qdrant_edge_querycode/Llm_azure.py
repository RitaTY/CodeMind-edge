
from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncAzureOpenAI

from qdrant_edge_querycode.config import (
    AZURE_ENDPOINT,
    AZURE_KEY,
    AZURE_VERSION,
    AZURE_DEPLOYMENT,
)

_client: AsyncAzureOpenAI | None = None

def _get_client() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_KEY,
            api_version=AZURE_VERSION,
        )
    return _client

async def _chat(system: str, user: str, timeout: float = 30.0) -> str:
    client = _get_client()
    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        ),
        timeout=timeout,
    )
    return response.choices[0].message.content.strip()

async def async_summarize_chunk(chunk: dict[str, Any]) -> str:
    system = (
        "You are a senior software engineer. "
        "Your job is to summarize what a code snippet does in ONE short sentence (max 20 words). "
        "Be concrete and specific — mention key behaviours like 'retries with backoff', "
        "'validates JWT tokens', 'pools database connections', etc. "
        "Do NOT say 'This function'. Just describe the behaviour directly."
    )
    user = (
        f"File: {chunk['file']}\n"
        f"Name: {chunk['name']}\n\n"
        f"```{chunk['language']}\n{chunk['code'][:800]}\n```"
    )
    return await _chat(system, user, timeout=20.0)

def summarize_chunk(chunk: dict[str, Any]) -> str:
    try:
        return asyncio.run(async_summarize_chunk(chunk))
    except Exception:
        first = chunk["code"].strip().splitlines()[0][:120]
        return first

async def async_answer_query(query: str, results: list[dict[str, Any]]) -> str:
    formatted_snippets = []
    for i, r in enumerate(results, 1):
        payload = r.get("payload", r)
        snippet = (
            f"--- Snippet {i} ---\n"
            f"File: {payload.get('file', '?')}  "
            f"(line {payload.get('start_line', '?')})\n"
            f"Function: {payload.get('name', '?')}\n"
            f"Summary: {payload.get('summary', 'N/A')}\n\n"
            f"```{payload.get('language', '')}\n"
            f"{payload.get('code', '')[:600]}\n"
            f"```"
        )
        formatted_snippets.append(snippet)
    context = "\n\n".join(formatted_snippets)
    system = (
        "You are an expert code assistant helping a developer understand a codebase. "
        "You receive a question and a set of relevant code snippets retrieved via semantic search. "
        "Your job is to:\n"
        "1. Directly answer the question\n"
        "2. Reference specific files and function names\n"
        "3. Explain the logic clearly in plain English\n"
        "4. Point out any relevant patterns or design decisions\n"
        "Be concise but thorough. Always mention the file path and function name."
    )
    user = (
        f"Question: {query}\n\n"
        f"Retrieved code snippets:\n\n{context}\n\n"
        f"Please answer the question based on these snippets."
    )
    return await _chat(system, user, timeout=60.0)

def answer_query(query: str, results: list[dict[str, Any]]) -> str:
    try:
        return asyncio.run(async_answer_query(query, results))
    except Exception as e:
        return f"[LLM error: {e}]\n\nTop match: {results[0].get('payload', {}).get('file', '?')} — {results[0].get('payload', {}).get('name', '?')}"
