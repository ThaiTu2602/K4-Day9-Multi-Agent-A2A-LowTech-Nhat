import zipfile
from pathlib import Path

def create_zips():
    p = Path('output')
    files = sorted(p.glob('EC_*.json'))
    
    # 1. Zip with output/ folder
    zip_path1 = Path('output.zip')
    if zip_path1.exists():
        zip_path1.unlink()
    with zipfile.ZipFile(zip_path1, 'w', zipfile.ZIP_DEFLATED) as z1:
        for f in files:
            z1.write(f, f.as_posix())
    print(f"Created {zip_path1.name} (files inside output/ folder)")

    # 2. Zip directly (files at root of zip)
    zip_path2 = Path('output_no_prefix.zip')
    if zip_path2.exists():
        zip_path2.unlink()
    with zipfile.ZipFile(zip_path2, 'w', zipfile.ZIP_DEFLATED) as z2:
        for f in files:
            z2.write(f, f.name)
    print(f"Created {zip_path2.name} (files at root)")

if __name__ == "__main__":
    create_zips()
