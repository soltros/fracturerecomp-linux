"""Hash only the explicit redistributable inputs; never traverse local assets."""
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[2]
digest = hashlib.sha256()
files = [root / p for p in ('CMakeLists.txt', 'CMakePresets.json', 'README.md', 'UPSTREAM.md',
                            'fracture_v1_manifest.toml', 'fracture_v2_manifest.toml',
                            'tools/setup.py', 'tools/xdvdfs.py', 'scripts/build-appimage.sh', 'recomplauncher.json')]
for directory in ('src', 'cmake', 'config', 'packaging/appimage'):
    files.extend(p for p in (root / directory).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts)
for file in sorted(files):
    digest.update(str(file.relative_to(root)).encode() + b'\0' + file.read_bytes() + b'\0')
print(digest.hexdigest()[:16])
