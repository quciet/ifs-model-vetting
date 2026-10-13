"""Persistent protocol reuse, recovery from errors, and responsive shutdown."""
import pathlib
import subprocess
import sys
import tempfile
import unittest
from decoder_session import DecoderSession

class DecoderSessionTests(unittest.TestCase):
    def test_requests_reuse_process_and_recover_after_payload_error(self):
        code="import sys,json;\nfor line in sys.stdin:\n p=json.loads(line); print(json.dumps({'ok':p[0]!='bad','error':'bad payload'}),flush=True)"
        with tempfile.TemporaryDirectory() as folder:
            script=pathlib.Path(folder)/'decoder.py';script.write_text(code)
            with DecoderSession([sys.executable,str(script)],lambda job:None) as session:
                session.convert('good','target',None);pid=session.process.pid
                with self.assertRaises(ValueError):session.convert('bad','target',None)
                session.convert('good','target',None);self.assertEqual(session.process.pid,pid)
            self.assertIsNotNone(session.process.poll())
    def test_cancel_kills_inflight_request(self):
        code="import sys,time;\nfor line in sys.stdin:time.sleep(60)"
        calls=[0]
        class Cancelled(Exception):pass
        def check(job):
            calls[0]+=1
            if calls[0]>=3:raise Cancelled()
        with tempfile.TemporaryDirectory() as folder:
            script=pathlib.Path(folder)/'decoder.py';script.write_text(code)
            with self.assertRaises(Cancelled):
                with DecoderSession([sys.executable,str(script)],check) as session:session.convert('input','output',None)
            self.assertIsNotNone(session.process.poll())

if __name__=='__main__':unittest.main()
