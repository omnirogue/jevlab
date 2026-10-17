# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Real stdio protocol roundtrip and malformed-input regression coverage."""

import io
import json
import subprocess
import sys
import unittest

from jevlab_oss.mcp_server import Server, serve

INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}}
READY = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}


def request(method, params=None, request_id=2):
    return {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params or {}}


class MCP(unittest.TestCase):
    def server(self):
        server = Server()
        server.handle(INIT)
        server.handle(READY)
        return server

    def test_stdio_all_tools_and_no_notification_replies(self):
        messages = [INIT, READY, request('ping'), request('tools/list')]
        messages.extend(request('tools/call', {'name': name}) for name in
                        ('jevlab_bench', 'jevlab_calibrate', 'jevlab_bias_audit', 'jevlab_list_rubrics'))
        messages.append({'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'jevlab_bench'}})
        done = subprocess.run([sys.executable, '-m', 'jevlab_oss.mcp_server'], input='\n'.join(map(json.dumps, messages))+'\n', text=True, capture_output=True, timeout=10, check=True)
        replies = [json.loads(line) for line in done.stdout.splitlines()]
        self.assertEqual(done.stderr, '')
        self.assertEqual(len(replies), 7)
        self.assertEqual(len(replies[2]['result']['tools']), 4)
        for reply in replies[3:]:
            self.assertFalse(reply['result']['isError'])
            self.assertEqual(json.loads(reply['result']['content'][0]['text']), reply['result']['structuredContent'])

    def test_protocol_and_tool_error_boundaries(self):
        server = self.server()
        self.assertEqual(Server().handle(request('tools/list'))['error']['code'], -32002)
        self.assertEqual(server.handle([])['error']['code'], -32600)
        self.assertEqual(server.handle(request('unknown'))['error']['code'], -32601)
        for arguments in ({'n_bins': True}, {'n_bins': 0}, {'n_bins': '10'}, {'fixture': []}, {'pairs': {}}, {'output': '/tmp/output'}):
            result = server.handle(request('tools/call', {'name': 'jevlab_calibrate', 'arguments': arguments}))
            self.assertEqual(result['error']['code'], -32602)
        error = server.handle(request('tools/call', {'name': 'jevlab_calibrate', 'arguments': {'fixture': {}}}))
        self.assertTrue(error['result']['isError'])
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'id': 99, 'result': {}}))
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'jevlab_calibrate'}}))

    def test_malformed_line_does_not_poison_next_request(self):
        output = io.StringIO()
        serve(io.StringIO('not-json\n{"p": NaN}\n' + json.dumps(request('ping')) + '\n'), output)
        replies = list(map(json.loads, output.getvalue().splitlines()))
        self.assertEqual([r['error']['code'] for r in replies[:2]], [-32700, -32700])
        self.assertEqual(replies[-1]['result'], {})


if __name__ == '__main__':
    unittest.main()
