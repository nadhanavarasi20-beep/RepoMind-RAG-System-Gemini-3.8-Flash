from typing import List, Dict, Any
from pathlib import Path

def build_repo_dependency_graph(files_meta: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build interactive dependency graph of modules, files, and imports.
    Returns { "nodes": [...], "links": [...], "total_modules": int, "total_dependencies": int }.
    """
    nodes_map: Dict[str, Dict[str, Any]] = {}
    links: List[Dict[str, Any]] = []
    seen_links = set()
    
    # 1. Register all files as nodes
    for file_path, meta in files_meta.items():
        lang = meta.get("language", "text")
        lines = meta.get("lines_count", 1)
        symbols_count = meta.get("symbols_count", 0)
        
        nodes_map[file_path] = {
            "id": file_path,
            "label": Path(file_path).name,
            "type": "file",
            "language": lang,
            "size": max(12, min(40, 10 + int(lines / 20) + symbols_count * 2)),
            "lines": lines
        }

    # 2. Extract import relationships
    for file_path, meta in files_meta.items():
        imports = meta.get("imports", [])
        for imp in imports:
            imported_mod = imp.get("module", "")
            if not imported_mod:
                continue
                
            # Normalize import to check if it points to an internal repo file
            matched_target = None
            # e.g., "app.auth" -> "app/auth.py"
            cand_py = imported_mod.replace(".", "/") + ".py"
            cand_js = imported_mod.replace(".", "/") + ".js"
            cand_ts = imported_mod.replace(".", "/") + ".ts"
            
            for fpath in files_meta.keys():
                norm_fpath = fpath.replace("\\", "/")
                if norm_fpath == cand_py or norm_fpath == cand_js or norm_fpath == cand_ts:
                    matched_target = fpath
                    break
                elif norm_fpath.endswith("/" + cand_py) or norm_fpath.endswith("/" + cand_js):
                    matched_target = fpath
                    break
                elif Path(fpath).stem == imported_mod.split(".")[-1]:
                    matched_target = fpath
                    break
                    
            if matched_target and matched_target != file_path:
                link_key = f"{file_path}->{matched_target}"
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    links.append({
                        "source": file_path,
                        "target": matched_target,
                        "type": "imports",
                        "weight": 1
                    })
            else:
                # External dependency node (e.g. fastapi, pydantic, react)
                root_pkg = imported_mod.split(".")[0].strip()
                if root_pkg and len(root_pkg) > 1 and not root_pkg.startswith("."):
                    ext_id = f"ext:{root_pkg}"
                    if ext_id not in nodes_map:
                        nodes_map[ext_id] = {
                            "id": ext_id,
                            "label": root_pkg,
                            "type": "package",
                            "language": "library",
                            "size": 10,
                            "lines": 0
                        }
                    link_key = f"{file_path}->{ext_id}"
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        links.append({
                            "source": file_path,
                            "target": ext_id,
                            "type": "imports_external",
                            "weight": 1
                        })

    return {
        "nodes": list(nodes_map.values()),
        "links": links,
        "total_modules": len(nodes_map),
        "total_dependencies": len(links)
    }
