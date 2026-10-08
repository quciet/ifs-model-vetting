"""Build the comparison tool for Companion's official release catalog."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--python',required=True)
    parser.add_argument('--version',default='0.1.0')
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version):raise ValueError('Invalid package version')
    root=Path(__file__).resolve().parents[1]
    subprocess.run([args.python,'-m','PyInstaller',str(root/'packaging/ComparisonTool.spec'),'--noconfirm'],cwd=root,check=True)
    package=root/'dist/IFsComparison'
    for name in ['LICENSE','THIRD_PARTY_NOTICES.txt']:shutil.copyfile(root/name,package/name)
    shutil.copytree(root/'licenses',package/'licenses',dirs_exist_ok=True)
    manifest={'id':'ifs-model-vetting','name':'Compare Runs','version':args.version,'api_version':1,'platform':'win-x64','kind':'web-service','entrypoint':'IFsComparison.exe'}
    (package/'tool.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    release=root/'release';release.mkdir(exist_ok=True)
    destination=release/f'ifs-model-vetting-{args.version}-win-x64.ifstool'
    pending=destination.with_suffix('.partial')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(package.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(package).as_posix())
    with zipfile.ZipFile(pending) as archive:
        assert archive.testzip() is None
    pending.replace(destination)
    with destination.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    destination.with_suffix('.sha256').write_text(digest+'  '+destination.name+'\n',encoding='utf-8')
    print(json.dumps({'file':str(destination),'sha256':digest,'size':destination.stat().st_size}),flush=True)

if __name__=='__main__':main()
