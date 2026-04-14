import argparse
import json
import os
import time
import hashlib
from datetime import datetime, timezone

import numpy as np
from PIL import Image

try:
    import torch
except Exception as exc:  # pragma: no cover
    raise RuntimeError("torch is required for trainer artifacts") from exc

try:
    from safetensors.torch import save_file as safetensors_save_file
except Exception:  # pragma: no cover
    safetensors_save_file = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Character adapter trainer placeholder")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--mode", required=True, choices=["lora", "dreambooth"])
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--gender", required=True)
    parser.add_argument("--steps", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(f"[trainer] session={args.session_id} mode={args.mode} steps={args.steps}")
    print(f"[trainer] image={args.image_path}")
    print(f"[trainer] output={args.output_path}")

    # Simulate a short training phase while still deriving artifact values from image data.
    time.sleep(1.0)

    os.makedirs(os.path.dirname(args.output_path), exist_ok=True)

    with Image.open(args.image_path) as image:
        rgb = image.convert("RGB").resize((64, 64))
        image_arr = np.asarray(rgb, dtype=np.float32) / 255.0

    digest = hashlib.sha256(image_arr.tobytes()).digest()
    seed = int.from_bytes(digest[:8], "big") % (2**31 - 1)
    generator = torch.Generator("cpu").manual_seed(seed)
    mean_tensor = torch.tensor(image_arr.mean(axis=(0, 1)), dtype=torch.float32)
    std_tensor = torch.tensor(image_arr.std(axis=(0, 1)), dtype=torch.float32)
    adapter_tensor = torch.randn((16, 16), generator=generator, dtype=torch.float32)

    weights = {
        "storybook.adapter.mean_rgb": mean_tensor,
        "storybook.adapter.std_rgb": std_tensor,
        "storybook.adapter.latent": adapter_tensor,
    }

    extension = os.path.splitext(args.output_path)[1].lower()
    if extension == ".safetensors" and safetensors_save_file:
        safetensors_save_file(weights, args.output_path)
    elif extension in {".pt", ".bin", ".ckpt"}:
        torch.save(weights, args.output_path)
    else:
        # Fallback to JSON if an unsupported extension is requested.
        with open(args.output_path, "w", encoding="utf-8") as file:
            json.dump({"warning": "Unsupported extension for binary adapter artifact"}, file)

    payload = {
        "session_id": args.session_id,
        "mode": args.mode,
        "name": args.name,
        "gender": args.gender,
        "steps": args.steps,
        "seed": seed,
        "output_path": args.output_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Deterministic trainer artifact generated from input image fingerprint.",
    }
    with open(f"{args.output_path}.meta.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    print("[trainer] training complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
