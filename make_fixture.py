"""Create a synthetic coding request for the localhost benchmark client."""
import argparse
import hashlib
import json
from pathlib import Path
import random


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="Model selector from the local server")
    parser.add_argument("output", type=Path)
    parser.add_argument("--blocks", type=int, required=True)
    args = parser.parse_args()
    if args.blocks < 1:
        parser.error("--blocks must be positive")
    rng = random.Random(1234)
    blocks = ["def normalize(value):\n    return min(255, max(0, value))\n"]
    for index in range(args.blocks):
        scale, offset = rng.randrange(2, 200), rng.randrange(-1000, 1000)
        blocks.append(
            f"def transform_{index}(values):\n"
            f"    return [normalize(item * {scale} + ({offset})) for item in values]\n"
        )
    prompt = "Review this Python module:\n\n" + "\n".join(blocks)
    prompt += "\n\nWrite two runnable tests for normalize, including both clamp boundaries."
    request = {
        "model": args.model, "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024, "temperature": 1.0, "top_p": 0.95, "top_k": 20,
        "min_p": 0.0, "seed": 1234, "stream": True,
        "stream_options": {"include_usage": True},
    }
    body = json.dumps(request, separators=(",", ":")).encode()
    with args.output.open("xb") as output:
        output.write(body)
    print(hashlib.sha256(body).hexdigest())


if __name__ == "__main__":
    main()
