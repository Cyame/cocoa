/**
 * Parity helper: runs the TypeScript slash-parser on a single input and
 * prints JSON to stdout. Called by ``tests/test_phase9_portal.py::test_slash_parser_parity``
 * via ``bun run scripts/slash-parser-parity.ts "<input>"``.
 *
 * Usage: bun run scripts/slash-parser-parity.ts "<raw_text>"
 */
import { parse_turn } from "../src/lib/slash-parser.ts";

const input = process.argv[2] ?? "";
const result = parse_turn(input);
console.log(JSON.stringify(result));
