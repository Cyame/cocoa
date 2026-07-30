#!/usr/bin/env python3
"""Generate many BaseClass (神职) portrait candidates via MiniMax.

- 11 public 神职 × 5 variants each (v2-01..v2-05)
- Plus internal cerebellum-baseclass × 3 (not user-selectable; stock only)
- 2048×2048, clean plain dark backdrop, NO frame / seal / watermark / text
- Existing files >1KB are skipped

Requires MINIMAX_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "https://api.minimaxi.com/v1/image_generation"
ROOT = Path(__file__).resolve().parents[1] / "assets" / "base-classes" / "candidates"
VARIANTS = 5
WIDTH = 2048
HEIGHT = 2048

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
    "deep charcoal with muted teal and copper accents, "
    "sharp eyes, high detail skin and fabric, "
    "clean edges suitable for circular crop in a web app. "
    f"{NEG}"
)

# (slug, display, motif, tags for manifest note only)
PUBLIC: list[tuple[str, str, str]] = [
    ("mi-shi", "密士", "strategic planner sage, calm focused eyes, subtle constellation embroidery on dark coat, indigo-teal mood"),
    ("huan-ling", "唤灵", "intent analyst summoner, soft teal sigil glow near hands, listening posture, silver-teal accents"),
    ("an-xing", "暗行", "ultraworker solo full-stack coder, hooded operative, determined gaze, teal edge light, boulder-pusher energy"),
    ("an-ying", "暗影", "junior coder shadow twin, younger face, softer copper accents, apprentice look"),
    ("zhu-jin", "铸金", "forge engineer artisan, warm copper workshop light, confident stance, molten metal spark accents"),
    ("ling-shi", "灵视", "architecture oracle, cool cyan eye catchlights, contemplative half-profile, crystalline motifs subtle"),
    ("heng-pan", "衡判", "quality gate judge, balanced calm expression, slate and brass accents, stern fairness"),
    ("you-hun", "游魂", "explorer scout, wind-swept short cloak, agile silhouette, search-beam teal specular"),
    ("qian-zhi", "潜知", "librarian archivist, warm copper lamp catchlight, stacked knowledge vibe without readable books text"),
    ("bai-tong", "百瞳", "multimodal looker, subtle multi-iris reflections, aperture motif tiny, prismatic teal"),
    ("jiu-ri", "旧日", "elder overseer, weathered calm authority, distant horizon rim light, deep charcoal robe"),
]

INTERNAL: list[tuple[str, str, str]] = [
    ("cerebellum-baseclass", "小脑", "internal workspace cerebellum agent, androgynous calm coordinator, soft teal neural glow, not heroic, institutional"),
]


def require_key() -> str:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        print("MINIMAX_API_KEY is required", file=sys.stderr)
        sys.exit(1)
    return key


def generate(key: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": "image-01",
            "prompt": prompt,
            "response_format": "url",
            "n": 1,
            "prompt_optimizer": False,
            # Prefer explicit pixels; aspect_ratio would override and shrink to 1024.
            "width": WIDTH,
            "height": HEIGHT,
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("base_resp", {}).get("status_code", 1) != 0:
        raise RuntimeError(str(payload))
    urls = payload.get("data", {}).get("image_urls") or []
    if not urls:
        raise RuntimeError(str(payload))
    return urls[0]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "cocoa-asset-gen/2.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())


def one_job(key: str, dest: Path, prompt: str) -> tuple[str, bool, str]:
    rel = str(dest.relative_to(ROOT.parent.parent))
    if dest.exists() and dest.stat().st_size > 1000:
        return rel, True, "skip-exists"
    last = ""
    for attempt in range(1, 4):
        try:
            url = generate(key, prompt)
            download(url, dest)
            return rel, True, "ok"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(2 * attempt)
    return rel, False, last


def build_jobs() -> list[tuple[Path, str]]:
    jobs: list[tuple[Path, str]] = []
    for slug, name, motif in PUBLIC:
        for i in range(1, VARIANTS + 1):
            prompt = (
                f"Square avatar portrait of Cocoa BaseClass '{name}' ({slug}), variant {i}. "
                f"{motif}. {BASE}"
            )
            jobs.append((ROOT / slug / f"v2-{i:02d}.jpg", prompt))
    for slug, name, motif in INTERNAL:
        for i in range(1, 4):
            prompt = (
                f"Square internal-system avatar for '{name}' ({slug}), variant {i}. "
                f"{motif}. Hidden from user catalog. {BASE}"
            )
            jobs.append((ROOT / "_internal" / slug / f"v2-{i:02d}.jpg", prompt))
    return jobs


def main() -> None:
    key = require_key()
    jobs = build_jobs()
    print(f"jobs={len(jobs)} out={ROOT} size={WIDTH}x{HEIGHT}", flush=True)
    results: list[dict] = []
    workers = int(os.environ.get("ASSET_WORKERS", "3"))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one_job, key, dest, prompt): dest for dest, prompt in jobs}
        done = 0
        for fut in as_completed(futs):
            rel, ok, msg = fut.result()
            done += 1
            print(f"[{done}/{len(jobs)}] {'OK' if ok else 'FAIL'} {rel} ({msg})", flush=True)
            results.append({"path": rel, "ok": ok, "msg": msg})
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "width": WIDTH,
        "height": HEIGHT,
        "variants_per_public": VARIANTS,
        "counts": {
            "total": len(results),
            "ok": sum(1 for r in results if r["ok"]),
            "fail": sum(1 for r in results if not r["ok"]),
        },
        "files": results,
        "note": "Pick favorites later; copy chosen file to base-classes/{slug}.jpg",
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if any(not r["ok"] for r in results):
        sys.exit(2)
    print("all done", flush=True)


if __name__ == "__main__":
    main()
