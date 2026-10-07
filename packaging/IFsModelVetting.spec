# Build from App: python -m PyInstaller packaging/IFsModelVetting.spec --noconfirm
from pathlib import Path
root=Path(SPECPATH).parent
a=Analysis([str(root/'desktop_launcher.py')],pathex=[str(root)],binaries=[],
           datas=[(str(root/'index.html'),'.'),(str(root/'audit.js'),'.'),
                  (str(root/'decoder-runtime'),'decoder-runtime')],
           hiddenimports=['tkinter','tkinter.filedialog','tkinter.messagebox'],
           excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='IFsModelVetting',
        debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='IFsModelVetting')
