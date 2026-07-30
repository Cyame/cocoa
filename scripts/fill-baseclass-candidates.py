#!/usr/bin/env python3
"""Fill missing base-class candidate slots v2-01..v2-08 (skip existing)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "https://api.minimaxi.com/v1/image_generation"
ROOT = Path(__file__).resolve().parents[1] / "assets" / "base-classes" / "candidates"
NEG = (
    "Critical constraints: plain seamless dark charcoal backdrop only. "
    "NO watermark, NO logo, NO signature, NO artist mark, NO site URL, NO handle, "
    "NO Chinese seal, NO stamp, NO tarot frame, NO ornate border, NO picture frame, "
    "NO UI chrome, NO subtitle, NO caption, NO typography, NO letters, NO numbers, "
    "NO corner branding of any kind."
)
BASE = (
    "Photorealistic cinematic character portrait for a product avatar, "
    "head-and-shoulders centered, soft volumetric lighting, "
    "plain dark charcoal seamless studio backdrop only, "
    "deep charcoal with muted teal and copper accents, sharp eyes, high detail. "
    + NEG
)
PUBLIC = [
    ("mi-shi", "密士", "strategic planner sage, calm focused eyes, subtle constellation embroidery on dark coat"),
    ("huan-ling", "唤灵", "intent analyst summoner, soft teal sigil glow near hands, listening posture"),
    ("an-xing", "暗行", "ultraworker solo full-stack coder, hooded operative, determined gaze, teal edge light"),
    ("an-ying", "暗影", "junior coder shadow twin, younger face, softer copper accents"),
    ("zhu-jin", "铸金", "forge engineer artisan, warm copper workshop light, confident stance"),
    ("ling-shi", "灵视", "architecture oracle, cool cyan eye catchlights, contemplative half-profile"),
    ("heng-pan", "衡判", "quality gate judge, balanced calm expression, slate and brass accents"),
    ("you-hun", "游魂", "explorer scout, wind-swept short cloak, agile silhouette"),
    ("qian-zhi", "潜知", "librarian archivist, warm copper lamp catchlight, no readable text"),
    ("bai-tong", "百瞳", "multimodal looker, subtle multi-iris reflections, aperture motif tiny"),
    ("jiu-ri", "旧日", "elder overseer, weathered calm authority, distant horizon rim light"),
]


def gen(key: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": "image-01",
            "prompt": prompt,
            "response_format": "url",
            "n": 1,
            "prompt_optimizer": False,
            "width": 1024,
            "height": 1024,
        }
    ).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("base_resp", {}).get("status_code", 1) != 0:
        raise RuntimeError(payload)
    return payload["data"]["image_urls"][0]


def dl(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "cocoa-asset-gen/2.1"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def one(key: str, dest: Path, prompt: str) -> tuple[str, bool, str]:
    last = ""
    for attempt in range(1, 4):
        try:
            dl(gen(key, prompt), dest)
            return str(dest), True, "ok"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(2 * attempt)
    return str(dest), False, last


def main() -> None:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        sys.exit("MINIMAX_API_KEY required")
    jobs: list[tuple[Path, str]] = []
    for slug, name, motif in PUBLIC:
        for i in range(1, 9):
            dest = ROOT / slug / f"v2-{i:02d}.jpg"
            if dest.exists() and dest.stat().st_size > 1000:
                continue
            prompt = (
                f"Square avatar portrait of Cocoa BaseClass '{name}' ({slug}), variant {i}. "
                f"{motif}. {BASE}"
            )
            jobs.append((dest, prompt))
    print(f"jobs={len(jobs)}", flush=True)
    fail = 0
    with ThreadPoolExecutor(max_workers=int(os.environ.get("ASSET_WORKERS", "3"))) as pool:
        futs = [pool.submit(one, key, d, p) for d, p in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            path, ok, msg = fut.result()
            print(f"[{i}/{len(jobs)}] {'OK' if ok else 'FAIL'} {path} ({msg})", flush=True)
            if not ok:
                fail += 1
    raise SystemExit(2 if fail else 0)


if __name__ == "__main__":
    main()
