import hashlib
from typing import List, Dict, Any, Optional

def generate_chunk_id(file_path: str, start_line: int, end_line: int, content: str) -> str:
    digest = hashlib.sha256(f"{file_path}:{start_line}:{end_line}:{content[:64]}".encode('utf-8')).hexdigest()[:12]
    return f"chk_{digest}"

def chunk_code_file(
    file_path: str,
    content: str,
    language: str,
    symbols: Dict[str, Any],
    max_chunk_lines: int = 50,
    overlap_lines: int = 12
) -> List[Dict[str, Any]]:
    """
    Code-aware semantic chunker that preserves function/class boundaries
    and falls back to overlapping line chunks for contiguous scripts.
    """
    lines = content.splitlines()
    if not lines:
        return []
        
    chunks: List[Dict[str, Any]] = []
    covered_lines = set()
    
    # 1. First process explicit symbols (functions & methods)
    all_symbols = []
    for cls in symbols.get("classes", []):
        all_symbols.append({
            "name": cls.get("name"),
            "type": "class",
            "start_line": cls.get("start_line", 1),
            "end_line": cls.get("end_line", len(lines))
        })
    for fn in symbols.get("functions", []):
        fn_name = fn.get("name")
        parent = fn.get("parent_class")
        full_name = f"{parent}.{fn_name}" if parent else fn_name
        all_symbols.append({
            "name": full_name,
            "type": fn.get("type", "function"),
            "start_line": fn.get("start_line", 1),
            "end_line": fn.get("end_line", len(lines))
        })
        
    # Sort symbols by start_line
    all_symbols.sort(key=lambda s: s["start_line"])
    
    for sym in all_symbols:
        s_start = max(1, sym["start_line"])
        s_end = min(len(lines), sym["end_line"])
        if s_end < s_start:
            continue
            
        sym_lines = lines[s_start - 1 : s_end]
        sym_len = len(sym_lines)
        
        # If symbol fits in one chunk
        if sym_len <= max_chunk_lines:
            chunk_text = "\n".join(sym_lines)
            chunks.append({
                "id": generate_chunk_id(file_path, s_start, s_end, chunk_text),
                "file_path": file_path,
                "start_line": s_start,
                "end_line": s_end,
                "language": language,
                "symbol_name": sym["name"],
                "symbol_type": sym["type"],
                "content": chunk_text
            })
            for l in range(s_start, s_end + 1):
                covered_lines.add(l)
        else:
            # Sub-chunk the large function with header context
            header_prefix = sym_lines[0] if sym_lines else ""
            idx = 0
            while idx < sym_len:
                sub_end_idx = min(idx + max_chunk_lines, sym_len)
                sub_lines = sym_lines[idx:sub_end_idx]
                
                # Prepend signature if not the first sub-chunk
                if idx > 0 and header_prefix:
                    actual_text = f"// [Context: {sym['name']}]\n" + "\n".join(sub_lines)
                else:
                    actual_text = "\n".join(sub_lines)
                    
                actual_start = s_start + idx
                actual_end = s_start + sub_end_idx - 1
                
                chunks.append({
                    "id": generate_chunk_id(file_path, actual_start, actual_end, actual_text),
                    "file_path": file_path,
                    "start_line": actual_start,
                    "end_line": actual_end,
                    "language": language,
                    "symbol_name": sym["name"],
                    "symbol_type": sym["type"],
                    "content": actual_text
                })
                for l in range(actual_start, actual_end + 1):
                    covered_lines.add(l)
                    
                if sub_end_idx >= sym_len:
                    break
                idx += (max_chunk_lines - overlap_lines)

    # 2. Chunk remaining uncovered lines (module header, imports, top-level statements)
    curr_start = 1
    total_lines = len(lines)
    
    while curr_start <= total_lines:
        # Find next uncovered line
        while curr_start <= total_lines and curr_start in covered_lines:
            curr_start += 1
            
        if curr_start > total_lines:
            break
            
        curr_end = min(curr_start + max_chunk_lines - 1, total_lines)
        # Advance till we hit a covered line or max
        for line_num in range(curr_start, curr_end + 1):
            if line_num in covered_lines:
                curr_end = line_num - 1
                break
                
        if curr_end >= curr_start:
            chunk_slice = lines[curr_start - 1 : curr_end]
            chunk_text = "\n".join(chunk_slice).strip()
            if chunk_text:  # Avoid empty whitespace chunks
                chunks.append({
                    "id": generate_chunk_id(file_path, curr_start, curr_end, chunk_text),
                    "file_path": file_path,
                    "start_line": curr_start,
                    "end_line": curr_end,
                    "language": language,
                    "symbol_name": None,
                    "symbol_type": "code_block",
                    "content": "\n".join(chunk_slice)
                })
            curr_start = curr_end + 1
        else:
            curr_start += 1
            
    # Sort all chunks by start_line
    chunks.sort(key=lambda c: (c["file_path"], c["start_line"]))
    return chunks
