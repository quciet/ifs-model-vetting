"""Desktop entry point shared by source and bundled Windows builds."""
import json
import os
import pathlib
import sys
import threading
import traceback
import webbrowser


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--pick-folder':
        from folder_picker import select_folder
        select_folder(sys.argv[2],sys.argv[3])
        return
    import app
    app.initialize_storage()
    # Windowed executables have no console. Keep diagnostic logs local.
    log=(app.DATA_ROOT/'application.log').open('a',encoding='utf-8',buffering=1)
    sys.stdout=log
    sys.stderr=log
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        try:
            import tkinter as tk
            probe=tk.Tk();probe.withdraw();probe.destroy()
            result={'data_root':str(app.DATA_ROOT),'html':(app.ROOT/'index.html').exists(),
                    'javascript':(app.ROOT/'audit.js').exists(),'decoder':app.DECODER_EXE.exists(), 'tkinter_ok':True}
            server=app.create_server()
            threading.Thread(target=server.serve_forever,daemon=True).start()
            import urllib.request
            url=f'http://127.0.0.1:{server.server_port}'
            result['http_ok']=urllib.request.urlopen(url).status==200
            request={'a':sys.argv[2],'b':sys.argv[2],'variables':['GDP','POP','AGDEM'],'atol':0,'rtol':0}
            app.JOBS['packaged-test']={'status':'running'}
            app.compare('packaged-test',request)
            result['comparison']=app.JOBS['packaged-test']
            result['ok']=all(result[k] for k in ('html','javascript','decoder','http_ok','tkinter_ok')) and result['comparison']['status']=='complete' and all('error' not in s and s['changed']==0 for s in result['comparison']['report']['summaries'])
            server.shutdown();server.server_close()
        except Exception:
            result={'ok':False,'error':traceback.format_exc()}
        pathlib.Path(sys.argv[3]).write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
        return
    import tkinter as tk
    from tkinter import ttk,messagebox
    root=tk.Tk()
    root.title('IFs Model Vetting')
    root.geometry('480x260')
    root.resizable(False,False)
    try:
        server=app.create_server()
    except Exception as exc:
        messagebox.showerror('Unable to start IFs Model Vetting',str(exc),parent=root)
        root.destroy()
        return
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='IFs Model Vetting',font=('Segoe UI',18,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Compare IFs runs in your browser.\nYour model files stay on this computer.',font=('Segoe UI',11)).pack(anchor='w',pady=12)
    ttk.Label(frame,text='Closing this launcher stops the application.').pack(anchor='w',pady=4)
    buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=14)
    ttk.Button(buttons,text='Open comparison app',command=lambda:webbrowser.open(url)).pack(side='left')
    def close():
        with app.LOCK:
            running=any(j['status']=='running' for j in app.JOBS.values())
        if running and not messagebox.askyesno('Comparison running','A comparison is running. Quit and interrupt it?',parent=root):
            return
        server.shutdown();server.server_close();root.destroy()
    ttk.Button(buttons,text='Quit',command=close).pack(side='right')
    root.protocol('WM_DELETE_WINDOW',close)
    root.after(300,lambda:webbrowser.open(url))
    root.mainloop()


if __name__=='__main__':
    main()
