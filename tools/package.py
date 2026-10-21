"""Create a reproducible-layout portable release from an official Python runtime ZIP."""
import argparse, hashlib, shutil, zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runtime-zip',required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1];dist=root/'dist';dist.mkdir(exist_ok=True)
stage=dist/'NearDrop-1.0.0-Windows-x64'
if stage.exists():shutil.rmtree(stage)
stage.mkdir()
for name in ['app','docs','tests','tools','.github']:
    shutil.copytree(root/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','test-output'))
for name in ['NearDrop.exe','NearDrop.cmd','Start-source.cmd','README.md','LICENSE','THIRD-PARTY-NOTICES.md']:
    shutil.copy2(root/name,stage/name)
for cmd in stage.glob('*.cmd'): cmd.write_bytes(cmd.read_text().replace('\r\n','\n').replace('\n','\r\n').encode())
runtime=stage/'runtime';runtime.mkdir()
with zipfile.ZipFile(a.runtime_zip) as z:
    if not {'python.exe','python314.zip'} <= set(z.namelist()):raise SystemExit('Expected Python 3.14 Windows embeddable runtime.')
    for n in z.namelist():
        if Path(n).is_absolute() or '..' in Path(n).parts:raise SystemExit('Unsafe runtime archive.')
    z.extractall(runtime)
manifest=''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.relative_to(stage).as_posix()+'\n' for f in sorted(stage.rglob('*')) if f.is_file())
(stage/'CHECKSUMS.sha256').write_text(manifest)
archive=Path(shutil.make_archive(str(stage),'zip',dist,stage.name))
digest=hashlib.sha256(archive.read_bytes()).hexdigest();(dist/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n')
print(archive);print(digest)
