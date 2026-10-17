# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""MCP 2025-06-18: newline-delimited JSON-RPC 2.0 over stdio, standard library only.

Tools accept inline synthetic data or use bundled examples. They never execute
commands, read arbitrary paths, write reports, or open network connections.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from . import __version__, bench, fixtures, resources
from .calibration import BiasAuditor, calibrate_fixture

PROTOCOL_VERSION = "2025-06-18"
MAX_LINE = 1_048_576


def _schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "additionalProperties": False}


FIXTURE = {"type": "object", "description": "Synthetic v1 fixture; omit for bundled demo. At most 1000 items and 16 judges."}
BINS = {"type": "integer", "minimum": 1, "maximum": 1000, "default": 10}
PAIRS = {"type": "array", "items": {"type": "object"}, "minItems": 1, "maxItems": 1000,
         "description": "Synthetic matched response pairs with a, b, forward, swapped and optional judge/model IDs."}
TOOLS = [
    {"name": "jevlab_bench", "description": "Benchmark recorded judges on synthetic gold labels; default is an offline demo.",
     "inputSchema": _schema({"fixture": FIXTURE, "n_bins": BINS})},
    {"name": "jevlab_calibrate", "description": "Fit Platt, temperature and histogram scaling; return holdout reliability and thresholds as JSON.",
     "inputSchema": _schema({"fixture": FIXTURE, "n_bins": BINS, "pairs": PAIRS})},
    {"name": "jevlab_bias_audit", "description": "Measure position, length, format and provenance-based self-preference; default is synthetic.",
     "inputSchema": _schema({"pairs": PAIRS})},
    {"name": "jevlab_list_rubrics", "description": "Return the ten public Apache-2.0 rubric templates.",
     "inputSchema": _schema({})},
]
for _tool in TOOLS:
    _tool["annotations"] = {"readOnlyHint": True, "destructiveHint": False,
                            "idempotentHint": True, "openWorldHint": False}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _execute(name: str, arguments: dict) -> dict:
    if name == "jevlab_list_rubrics":
        return {"rubrics": resources.list_rubrics()}
    if "pairs" in arguments and not 1 <= len(arguments["pairs"]) <= 1000:
        raise ValueError("pairs must contain 1 to 1000 entries")
    if name == "jevlab_bias_audit":
        return BiasAuditor().audit(arguments.get("pairs", resources.default_pairs()))
    fixture = arguments.get("fixture", resources.default_fixture())
    fixtures.validate(fixture)
    if len(fixture["items"]) > 1000 or len(fixture["items"][0].get("judgments", {})) > 16:
        raise ValueError("MCP limit: 1000 items and 16 judges; use the Python API for larger inputs")
    bins = arguments.get("n_bins", 10)
    if name == "jevlab_bench":
        return bench.run(fixture, n_bins=bins)
    pairs = arguments.get("pairs", None if "fixture" in arguments else resources.default_pairs())
    return calibrate_fixture(fixture, bins, pairs)


class Server:
    def __init__(self) -> None:
        self.initialized = False
        self.ready = False

    def handle(self, request: object) -> dict | None:
        if not isinstance(request, dict):
            return _error(None, -32600, "Invalid Request")
        request_id = request.get("id")
        has_id = "id" in request
        if (request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str)
                or (has_id and type(request_id) not in (str, int))):
            # Client responses are not requests and never receive another response.
            if request.get("jsonrpc") == "2.0" and has_id and ("result" in request or "error" in request):
                return None
            return _error(None, -32600, "Invalid Request")
        method, params = request["method"], request.get("params", {})
        if not has_id:
            if method == "notifications/initialized" and self.initialized and isinstance(params, dict):
                self.ready = True
            return None  # Notifications, including tools/call, never invoke tools.
        if not isinstance(params, dict):
            return _error(request_id, -32602, "Parameters must be an object")
        if method == "ping":
            return _result(request_id, {})
        if method == "initialize":
            client = params.get("clientInfo")
            if (not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(client, dict)
                    or not all(isinstance(client.get(k), str) for k in ("name", "version"))):
                return _error(request_id, -32602, "initialize requires protocolVersion, capabilities and clientInfo")
            self.initialized, self.ready = True, False
            return _result(request_id, {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "jevlab", "version": __version__},
                "instructions": "Offline evaluation tools. All bundled data is synthetic. Supply inline data, never secrets."})
        if method not in ("tools/list", "tools/call"):
            return _error(request_id, -32601, "Method not found")
        if not self.ready:
            return _error(request_id, -32002, "Initialize and send notifications/initialized first")
        if method == "tools/list":
            if params:
                return _error(request_id, -32602, "This server does not paginate tools")
            return _result(request_id, {"tools": TOOLS})
        name, arguments = params.get("name"), params.get("arguments", {})
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            return _error(request_id, -32602, "Unknown tool")
        if not isinstance(arguments, dict) or set(arguments) - set(tool["inputSchema"]["properties"]):
            return _error(request_id, -32602, "Invalid tool arguments")
        if ("fixture" in arguments and not isinstance(arguments["fixture"], dict)
                or "pairs" in arguments and not isinstance(arguments["pairs"], list)
                or "n_bins" in arguments and (type(arguments["n_bins"]) is not int or not 1 <= arguments["n_bins"] <= 1000)):
            return _error(request_id, -32602, "Invalid argument type or range")
        try:
            value = _execute(name, arguments)
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(value, allow_nan=False)}],
                                       "structuredContent": value, "isError": False})
        except (ValueError, TypeError, KeyError) as exc:
            return _result(request_id, {"content": [{"type": "text", "text": f"Invalid evaluation data: {exc}"}], "isError": True})
        except Exception:
            # No tracebacks, paths or environment values on the protocol stream.
            return _error(request_id, -32603, "Internal evaluation error")


def serve(stdin: TextIO, stdout: TextIO) -> None:
    server = Server()
    while True:
        line = stdin.readline(MAX_LINE + 1)
        if not line:
            break
        if len(line) > MAX_LINE:
            while line and not line.endswith("\n"):
                line = stdin.readline(MAX_LINE + 1)
            response = _error(None, -32600, "Message exceeds 1 MiB character limit")
        else:
            try:
                def invalid_constant(value: str):
                    raise ValueError("JSON constants must be finite")
                request = json.loads(line, parse_constant=invalid_constant)
                response = server.handle(request)
            except (ValueError, RecursionError):
                response = _error(None, -32700, "Parse error")
        if response is not None:
            stdout.write(json.dumps(response, allow_nan=False, separators=(",", ":")) + "\n")
            stdout.flush()


def main() -> int:
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
        serve(sys.stdin, sys.stdout)
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
