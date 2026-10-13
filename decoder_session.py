"""One lazy decoder process per comparison session, with cancellable requests."""
import json
import os
import queue
import subprocess
import threading

class DecoderSession:
    def __init__(self, command, check_cancel):
        self.command=command; self.check_cancel=check_cancel; self.process=None
        self.responses=queue.Queue(); self.reader=None; self.inflight=False
    def __enter__(self): return self
    def convert(self, source, target, job):
        self.check_cancel(job)
        if self.process is None:
            self.process=subprocess.Popen(self.command+['--serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            def read():
                for line in self.process.stdout: self.responses.put(line)
                self.responses.put(None)
            self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        self.inflight=True
        self.process.stdin.write(json.dumps([str(source),str(target)])+'\n');self.process.stdin.flush()
        while True:
            self.check_cancel(job)
            try:line=self.responses.get(timeout=.1)
            except queue.Empty:continue
            if line is None:raise ValueError('IFs decoder exited unexpectedly')
            self.inflight=False
            result=json.loads(line)
            if not result.get('ok'):raise ValueError('IFs decoder failed: '+result.get('error','Unknown error'))
            return
    def __exit__(self, exc_type, exc, tb):
        if self.process is None:return
        try:
            if (exc_type is not None or self.inflight) and self.process.poll() is None:self.process.kill()
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        finally:
            if self.reader:self.reader.join(timeout=2)
            self.process.stdout.close()
