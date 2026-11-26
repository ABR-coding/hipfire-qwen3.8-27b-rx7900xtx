"""Measure one sampled SSE request against a local HipFire instance."""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    request = urllib.request.Request(
        f"http://127.0.0.1:{args.port}/v1/chat/completions",
        data=args.request.read_bytes(),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    first = usage = finish = None
    start = time.perf_counter()
    with opener.open(request, timeout=300) as response:
        for line in response:
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                end = time.perf_counter()
                break
            frame = json.loads(payload)
            if frame.get("error"):
                raise RuntimeError(frame["error"])
            usage = frame.get("usage") or usage
            for choice in frame.get("choices", []):
                delta = choice.get("delta") or {}
                if first is None and any(delta.get(k) for k in (
                    "content", "reasoning_content", "reasoning"
                )):
                    first = time.perf_counter()
                finish = choice.get("finish_reason") or finish
        else:
            raise RuntimeError("Missing SSE completion marker")
    if first is None or not usage or not finish:
        raise RuntimeError("Missing content, usage or finish reason")
    print(json.dumps({
        "usage": usage,
        "finish": finish,
        "ttft_s": first - start,
        "wall_s": end - start,
        "decode_interval_s": end - first,
        "decode_tok_s": (usage["completion_tokens"] - 1) / (end - first),
    }, indent=2))


if __name__ == "__main__":
    main()
