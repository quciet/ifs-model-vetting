"""Cancellation must interrupt an active decoder and reap its process."""
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
import app

class StopTests(unittest.TestCase):
    def test_stop_terminates_active_decoder(self):
        job='stop-test'
        app.JOBS[job]={'status':'running'}
        started=threading.Event(); processes=[]; errors=[]
        original_popen=subprocess.Popen
        def slow_decoder(command, **kwargs):
            process=original_popen([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
            processes.append(process);started.set();return process
        class Database:
            def execute(self,*args):return self
            def fetchone(self):return (b'test payload',)
        def worker():
            try:app.decode(Database(),'GDP',[1,2],job)
            except Exception as error:errors.append(error)
        try:
            with patch.object(app.subprocess,'Popen',side_effect=slow_decoder):
                thread=threading.Thread(target=worker);thread.start()
                self.assertTrue(started.wait(3))
                app.JOBS[job]['stop_requested']=True
                thread.join(3)
                self.assertFalse(thread.is_alive(),'Cancellation waited for the decoder to finish')
                self.assertIsInstance(errors[0],app.ComparisonStopped)
                self.assertIsNotNone(processes[0].poll(),'Decoder process was left running')
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.wait()
            app.JOBS.pop(job,None)

if __name__=='__main__':unittest.main()
