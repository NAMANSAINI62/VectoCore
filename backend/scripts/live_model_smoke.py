"""Make a small real provider request to each configured chatbot model.

Run from backend/: python scripts/live_model_smoke.py
The script prints status and latency only; it never prints credentials or responses.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.llm.registry import available_models, get_chat_model


async def check_model(provider: str, model_id: str, timeout_seconds: float = 15.0) -> tuple[str, str]:
    started = time.perf_counter()
    try:
        async def _stream() -> str:
            chunks: list[str] = []
            async for chunk in get_chat_model(provider, model_id, streaming=True).astream(
                "Reply with exactly the word OK."
            ):
                content = chunk.content
                if isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, list):
                    chunks.extend(
                        block["text"] for block in content
                        if isinstance(block, dict) and isinstance(block.get("text"), str)
                    )
            return "".join(chunks).strip()

        text = await asyncio.wait_for(_stream(), timeout=timeout_seconds)
        if not text:
            return "FAIL", f"{provider}/{model_id}: empty streamed response"
        elapsed = int((time.perf_counter() - started) * 1000)
        return "PASS", f"{provider}/{model_id}: streamed response received in {elapsed} ms"
    except asyncio.TimeoutError:
        elapsed = int((time.perf_counter() - started) * 1000)
        return "FAIL", f"{provider}/{model_id}: timed out after {elapsed} ms"
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        code = getattr(exc, "status_code", None)
        status = f"HTTP {code}" if isinstance(code, int) else type(exc).__name__
        return "FAIL", f"{provider}/{model_id}: {status} after {elapsed} ms"


async def main() -> int:
    models = available_models()
    print(f"Checking {len(models)} configured models...", flush=True)
    results: list[tuple[str, str]] = []
    for item in models:
        outcome, summary = await check_model(item.provider, item.id)
        results.append((outcome, summary))
        print(f"{outcome} {summary}", flush=True)
    failures = sum(outcome == "FAIL" for outcome, _ in results)
    print(f"\n{len(results) - failures}/{len(results)} models passed", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
