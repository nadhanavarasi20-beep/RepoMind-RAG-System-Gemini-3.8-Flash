import os
import zipfile
from pathlib import Path
from typing import Tuple, List

MAX_TOTAL_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_ENTRY_COUNT = 5_000

class ZipSecurityError(Exception):
    pass

def extract_safe_zip(zip_filepath: Path, target_dir: Path) -> Tuple[int, int]:
    """
    Safely extract a ZIP archive while preventing ZipSlip and Zip Bomb attacks.
    Returns (extracted_files_count, total_uncompressed_bytes).
    """
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    
    total_uncompressed = 0
    file_count = 0
    
    with zipfile.ZipFile(zip_filepath, 'r') as zf:
        infolist = zf.infolist()
        if len(infolist) > MAX_ENTRY_COUNT:
            raise ZipSecurityError(f"Archive exceeds maximum allowed entries limit ({len(infolist)} > {MAX_ENTRY_COUNT})")
            
        for member in infolist:
            # ZipSlip prevention: resolve target destination
            member_path = member.filename
            
            # Reject absolute paths or suspicious prefixes
            if member_path.startswith('/') or member_path.startswith('\\') or '..' in member_path:
                norm = os.path.normpath(member_path)
                if norm.startswith('..') or os.path.isabs(norm):
                    raise ZipSecurityError(f"Potentially malicious archive entry detected: {member.filename}")
            
            destination = (target_dir / member_path).resolve()
            
            # Ensure destination is strictly inside target_dir
            try:
                destination.relative_to(target_dir)
            except ValueError:
                raise ZipSecurityError(f"Path traversal detected in archive entry: {member.filename}")
                
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ZipSecurityError("Archive uncompressed size exceeds safe limit (Zip Bomb protection).")
                
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(destination, 'wb') as target:
                    # Write in 64KB blocks
                    while True:
                        block = source.read(65536)
                        if not block:
                            break
                        target.write(block)
                file_count += 1
                
    return file_count, total_uncompressed
