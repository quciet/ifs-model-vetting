from pathlib import Path
root=Path(SPECPATH).parent
a=Analysis([str(root/'comparison_tool.py')],pathex=[str(root)],binaries=[],
    datas=[(str(root/'index.html'),'.'),(str(root/'audit.js'),'.'),(str(root/'decoder-runtime'),'decoder-runtime')],
    hiddenimports=['app','diagnostics','folder_picker','tkinter','tkinter.filedialog','tkinter.messagebox'],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='IFsComparison',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='IFsComparison')
