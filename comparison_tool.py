"""Self-contained comparison service for IFsCompanion tool packages."""
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlparse
import app

class Handler(app.Handler):
    def authorized(self):
        token=os.environ.get('IFS_TOOL_TOKEN','')
        if not token or not secrets.compare_digest(self.headers.get('X-IFs-Tool-Token',''),token):
            self.send({'error':'Open this tool through IFsCompanion.'},status=403)
            return False
        return True
    def do_GET(self):
        if not self.authorized():return
        if urlparse(self.path).path=='/bridge/status':
            with app.LOCK:return self.send({'running':any(j['status']=='running' for j in app.JOBS.values())})
        if self.path=='/':
            html=(app.ROOT/'index.html').read_text(encoding='utf-8')
            style='<style>body{background:white}main{padding:8px 4px;max-width:none}#installation,#browse,#scan,#installationPaths{display:none}section:first-of-type>label:first-child,section:first-of-type>p:first-of-type{display:none}#openSettings{display:inline-block}</style>'
            return self.send(html.replace('<main>',style+'<main>',1).encode(),'text/html; charset=utf-8')
        return super().do_GET()
    def do_POST(self):
        if not self.authorized():return
        if self.path=='/bridge/shutdown':
            self.send({'ok':True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()
            return
        return super().do_POST()

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--pick-folder':
        from folder_picker import select_folder
        select_folder(sys.argv[2],sys.argv[3]);return
    if not os.environ.get('IFS_TOOL_TOKEN'):raise RuntimeError('Install and open this package through IFsCompanion.')
    server=app.create_server()
    server.RequestHandlerClass=Handler
    ready=Path(os.environ['IFS_TOOL_READY_FILE'])
    temporary=ready.with_suffix('.tmp')
    temporary.write_text(json.dumps({'port':server.server_port}),encoding='utf-8')
    temporary.replace(ready)
    def lifetime():
        sys.stdin.buffer.read()
        server.shutdown()
    threading.Thread(target=lifetime,daemon=True).start()
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
