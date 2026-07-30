#!/usr/bin/env python3
"""Generate Cocoa art assets via MiniMax image_generation API.

Requires env MINIMAX_API_KEY. Does not write the key anywhere.
Downloads JPEG URLs into assets/ under the repo root.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "https://api.minimaxi.com/v1/image_generation"
ROOT = Path(__file__).resolve().parents[1] / "assets"
STYLE = (
    "cinematic character concept art for a multi-agent control studio, "
    "deep charcoal and muted teal-copper palette, soft volumetric light, "
    "subtle occult laboratory atmosphere, no text, no watermark, no logo, "
    "no UI chrome, high detail, cohesive product art direction"
)

BASE_CLASSES: list[tuple[str, str, str]] = [
    ("mi-shi", "密士", "strategic planner sage, calm focused eyes, parchment and constellation motifs, indigo-teal cloak silhouette"),
    ("huan-ling", "唤灵", "intent analyst summoner, soft glow sigils around hands, listening posture, silver-teal accents"),
    ("an-xing", "暗行", "solo full-stack coder operative, hooded, keyboard and circuit motifs, sharp teal edge light"),
    ("an-ying", "暗影", "junior coder shadow twin, lighter younger face, softer copper accents, apprentice cloak"),
    ("zhu-jin", "铸金", "forge artisan engineer, hammer and molten copper sparks, confident stance, workshop heat glow"),
    ("ling-shi", "灵视", "architecture oracle, crystalline eye motifs, cool cyan light, contemplative half-profile"),
    ("heng-pan", "衡判", "quality gate judge, balanced scales motif, stern calm face, slate and brass accents"),
    ("you-hun", "游魂", "explorer scout, wind-swept cloak, map fragments and search beams, agile silhouette"),
    ("qian-zhi", "潜知", "librarian archivist, stacked books and glowing references, warm copper lamp light"),
    ("bai-tong", "百瞳", "multimodal looker, many subtle iris reflections, camera aperture motifs, prismatic teal"),
    ("jiu-ri", "旧日", "elder overseer Atlas, weathered calm authority, distant horizon light, deep charcoal robe"),
]

AVATAR_PROMPTS = [
    "androgynous young operator portrait, short dark hair, soft teal rim light",
    "woman operator portrait, neat bun, copper earrings, calm studio lighting",
    "man operator portrait, cropped beard, charcoal coat, cool key light",
    "nonbinary operator portrait, silver hair streak, teal scarf, soft bokeh",
    "young researcher portrait, round glasses, warm desk lamp glow",
    "senior director portrait, greying temples, confident half-smile, brass accents",
    "east-asian woman operator, bob cut, muted teal blouse, shallow depth of field",
    "south-asian man operator, thoughtful gaze, charcoal turtleneck, soft fill",
    "black woman operator, braided hair, copper jewelry, cinematic portrait",
    "latin man operator, short curls, teal hoodie under coat, studio backdrop",
    "pale androgynous operator, freckles, soft copper rim, quiet expression",
    "older woman operator, silver bob, sharp eyes, slate blazer",
    "young man operator, undercut, earpiece hint, teal specular highlights",
    "woman operator with hijab in charcoal fabric, warm copper catchlights",
    "athletic operator portrait, short hair, teal athletic zip, focused look",
    "soft-featured operator, messy bun, reading glasses pushed up, amber desk glow",
]

ENTITY_TINTS = [
    ("tint-teal", "accent color pure teal"),
    ("tint-copper", "accent color warm copper"),
    ("tint-amber", "accent color muted amber gold"),
    ("tint-crimson", "accent color deep crimson"),
    ("tint-sage", "accent color sage green"),
    ("tint-slate-blue", "accent color slate blue"),
    ("tint-rose", "accent color dusty rose"),
    ("tint-gold", "accent color antique gold"),
    ("tint-cyan", "accent color electric cyan"),
    ("tint-charcoal", "accent color near-black charcoal with white edge"),
    ("tint-indigo", "accent color deep indigo blue, not purple neon"),
    ("tint-olive", "accent color olive bronze"),
]

BACKGROUNDS = [
    ("login-atmosphere-01", "16:9", "wide empty control room at night, soft teal monitor glow, charcoal architecture, no people, no text"),
    ("login-atmosphere-02", "16:9", "abstract deep ocean abyss with faint copper constellation lines, cinematic, no text"),
    ("namespace-hub-01", "16:9", "top-down abstract workspace map of glowing nodes and corridors, teal and copper on charcoal, no labels"),
    ("namespace-hub-02", "16:9", "soft gradient laboratory wall with subtle hexagonal lattice, dark slate, ambient light"),
    ("ide-canvas-01", "16:9", "empty topology canvas texture, dark paper with faint grid and dust motes, teal pin lights"),
    ("ide-canvas-02", "16:9", "blurred out-of-focus server racks bokeh, charcoal and copper, cinematic depth"),
    ("onboarding-hero-01", "16:9", "ritual summoning circle of soft light on dark floor, teal and copper, no symbols readable as text"),
    ("card-surface-01", "1:1", "subtle matte card texture charcoal with fine noise, soft vignette, product UI background"),
]

MISC = [
    ("empty-state-entities", "1:1", "empty pedestal in dark hall, soft teal spotlight, waiting for a figure, no text"),
    ("empty-state-workspace", "1:1", "blank circular table in control room, chairs empty, copper rim light, no text"),
    ("glow-node-teal", "1:1", "single glowing circular node icon, soft teal bloom on transparent-looking black, simple"),
    ("glow-node-copper", "1:1", "single glowing circular node icon, soft copper bloom on black, simple"),
    ("passage-flow", "1:1", "abstract flowing light ribbon between two nodes, teal to copper gradient, black background"),
    ("memory-orb", "1:1", "small crystalline memory orb floating, teal internal light, black background"),
    ("vault-seal", "1:1", "circular metallic seal emblem abstract, brass and charcoal, no letters"),
    ("loading-spiral", "1:1", "subtle spiral of soft particles, teal copper charcoal, abstract loading motif, no text"),
]


def require_key() -> str:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        print("MINIMAX_API_KEY is required", file=sys.stderr)
        sys.exit(1)
    return key


def generate(key: str, prompt: str, aspect_ratio: str = "1:1", n: int = 1) -> list[str]:
    body = json.dumps(
        {
            "model": "image-01",
            "prompt": prompt,
            "response_format": "url",
            "n": n,
            "prompt_optimizer": False,
            "aspect_ratio": aspect_ratio,
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("base_resp", {}).get("status_code", 1) != 0:
        raise RuntimeError(f"API error: {payload}")
    urls = payload.get("data", {}).get("image_urls") or []
    if not urls:
        raise RuntimeError(f"No image_urls: {payload}")
    return urls


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "cocoa-asset-gen/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def job_generate_one(
    key: str,
    dest: Path,
    prompt: str,
    aspect_ratio: str,
    retries: int = 3,
) -> tuple[str, bool, str]:
    if dest.exists() and dest.stat().st_size > 1000:
        return (str(dest.relative_to(ROOT)), True, "skip-exists")
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            urls = generate(key, prompt, aspect_ratio=aspect_ratio, n=1)
            download(urls[0], dest)
            return (str(dest.relative_to(ROOT)), True, "ok")
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            time.sleep(2 * attempt)
    return (str(dest.relative_to(ROOT.parent)), False, last_err)


def build_jobs() -> list[tuple[Path, str, str]]:
    jobs: list[tuple[Path, str, str]] = []
    for slug, name, motif in BASE_CLASSES:
        prompt = (
            f"Square portrait emblem of Cocoa BaseClass '{name}' ({slug}): {motif}. "
            f"Half-body character centered, iconic and memorable. {STYLE}"
        )
        jobs.append((ROOT / "base-classes" / f"{slug}.jpg", prompt, "1:1"))
        # secondary pose / alt for later UI
        alt = (
            f"Alternate square icon bust for Cocoa BaseClass '{name}': {motif}, "
            f"more emblematic and simpler silhouette, still recognizable. {STYLE}"
        )
        jobs.append((ROOT / "base-classes" / f"{slug}-alt.jpg", alt, "1:1"))

    for i, portrait in enumerate(AVATAR_PROMPTS, start=1):
        prompt = f"Default user avatar portrait: {portrait}. {STYLE}"
        jobs.append((ROOT / "avatars" / f"default-{i:02d}.jpg", prompt, "1:1"))

    for slug, tint in ENTITY_TINTS:
        prompt = (
            "Generic AI entity companion figure, androgynous stylized, same pose and design, "
            f"only recolored with {tint}, soft studio lighting, square crop. {STYLE}"
        )
        jobs.append((ROOT / "entities" / f"{slug}.jpg", prompt, "1:1"))

    for name, ratio, desc in BACKGROUNDS:
        prompt = f"{desc}. {STYLE}"
        jobs.append((ROOT / "backgrounds" / f"{name}.jpg", prompt, ratio))

    for name, ratio, desc in MISC:
        prompt = f"{desc}. {STYLE}"
        jobs.append((ROOT / "misc" / f"{name}.jpg", prompt, ratio))

    return jobs


def main() -> None:
    key = require_key()
    jobs = build_jobs()
    print(f"jobs={len(jobs)} root={ROOT}", flush=True)
    results: list[dict] = []
    # modest parallelism to avoid rate limits
    workers = int(os.environ.get("ASSET_WORKERS", "3"))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(job_generate_one, key, dest, prompt, ratio): dest
            for dest, prompt, ratio in jobs
        }
        done = 0
        for fut in as_completed(futs):
            rel, ok, msg = fut.result()
            done += 1
            status = "OK" if ok else "FAIL"
            print(f"[{done}/{len(jobs)}] {status} {rel} ({msg})", flush=True)
            results.append({"path": rel, "ok": ok, "msg": msg})

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "style": STYLE,
        "base_classes": [s for s, _, _ in BASE_CLASSES],
        "counts": {
            "total": len(results),
            "ok": sum(1 for r in results if r["ok"]),
            "fail": sum(1 for r in results if not r["ok"]),
        },
        "files": results,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fails = [r for r in results if not r["ok"]]
    if fails:
        print(f"FAILED {len(fails)} jobs", file=sys.stderr)
        sys.exit(2)
    print("all done", flush=True)


if __name__ == "__main__":
    main()
