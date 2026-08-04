"""P9 Portal parity tests.

Verifies that the TypeScript slash-parser mirror (``cocoa-portal/src/lib/slash-parser.ts``)
produces output identical to the Python reference parser
(``app/core/slash_parser.py::parse_turn``).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.slash_parser import parse_turn

WORKTREE_ROOT = Path(__file__).resolve().parent.parent.parent
PORTAL_DIR = WORKTREE_ROOT / "cocoa-portal"
PARITY_SCRIPT = PORTAL_DIR / "scripts" / "slash-parser-parity.ts"

BUN = shutil.which("bun")

PARITY_INPUTS = [
    "@密士 /plan @workspace:foo.md",
    "hello world",
    "@unknown /plan",
    "broadcast\n@alice /read\n@bob /write @workspace:notes.md",
    "",
    "@alice /plan arg1 arg2 @fornix:key",
    "/global-cmd",
    "@alice /cmd with @vault:doc/path",
    "   \n  \n  ",
    "@bob /read @workspace:a.md @workspace:b.md",
    # v4.5 scope normalization: legacy scopes → hub/instance, new pass through.
    "@carol /read @memory:lesson:intro",
    "@dave /write @blackboard:shared/doc.md",
    "@erin /plan @hub:shared/plan.md @instance:notes/a.md",
    "@frank /read @vault:archive/key @workspace:other/path",
]


def _run_ts_parser(raw_text: str) -> dict:
    result = subprocess.run(
        [BUN, "run", str(PARITY_SCRIPT), raw_text],
        capture_output=True,
        text=True,
        cwd=str(PORTAL_DIR),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"bun script failed (exit {result.returncode}):\n{result.stderr}"
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(BUN is None, reason="bun not found in PATH")
@pytest.mark.parametrize("raw_text", PARITY_INPUTS)
def test_slash_parser_parity(raw_text: str) -> None:
    py_turn = parse_turn(raw_text).model_dump()
    ts_turn = _run_ts_parser(raw_text)
    assert py_turn == ts_turn, (
        f"Parser mismatch for input {raw_text!r}\n"
        f"  Python: {json.dumps(py_turn, ensure_ascii=False, sort_keys=True)}\n"
        f"  TS:     {json.dumps(ts_turn, ensure_ascii=False, sort_keys=True)}"
    )
