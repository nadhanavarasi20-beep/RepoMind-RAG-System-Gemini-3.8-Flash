import re
from typing import List, Dict, Any

# JS/TS regex patterns
JS_FUNC_RE = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)", re.MULTILINE)
JS_ARROW_RE = re.compile(r"^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", re.MULTILINE)
JS_CLASS_RE = re.compile(r"^(?:export\s+)?(?:default\s+)?class\s+([a-zA-Z0-9_$]+)(?:\s+extends\s+([a-zA-Z0-9_$]+))?", re.MULTILINE)
JS_IMPORT_RE = re.compile(r"^import\s+(?:\{([^}]+)\}|([a-zA-Z0-9_$]+))\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)

# Go regex patterns
GO_FUNC_RE = re.compile(r"^func\s+(?:\((?:[a-zA-Z0-9_*\s]+)\)\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)", re.MULTILINE)
GO_TYPE_RE = re.compile(r"^type\s+([a-zA-Z0-9_]+)\s+(?:struct|interface)", re.MULTILINE)
GO_IMPORT_RE = re.compile(r"^\s*\"([^\"]+)\"", re.MULTILINE)

# Rust regex patterns
RS_FN_RE = re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", re.MULTILINE)
RS_STRUCT_RE = re.compile(r"^(?:pub\s+)?(?:struct|enum|trait)\s+([a-zA-Z0-9_]+)", re.MULTILINE)
RS_USE_RE = re.compile(r"^use\s+([^;]+);", re.MULTILINE)

# Java / C++ regex patterns
JAVA_METHOD_RE = re.compile(r"^\s*(?:public|protected|private|static|\s)+[\w<>\[\]]+\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*\{", re.MULTILINE)
JAVA_CLASS_RE = re.compile(r"^\s*(?:public|protected|private|static|\s)*(?:class|interface|record)\s+([a-zA-Z0-9_]+)", re.MULTILINE)
CPP_INCLUDE_RE = re.compile(r"^#include\s+[<\"']([^>\"']+)[\">']", re.MULTILINE)

def parse_multi_lang(source_code: str, language: str) -> Dict[str, Any]:
    """Parse non-python source code into structured symbols, classes, functions, and imports."""
    lines = source_code.splitlines()
    classes = []
    functions = []
    imports = []
    
    if language in ("javascript", "typescript"):
        # Classes
        for m in JS_CLASS_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            classes.append({
                "name": m.group(1),
                "type": "class",
                "start_line": start_line,
                "end_line": min(start_line + 40, len(lines)),
                "docstring": "",
                "bases": [m.group(2)] if m.group(2) else []
            })
        # Functions
        for m in JS_FUNC_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            functions.append({
                "name": m.group(1),
                "type": "function",
                "start_line": start_line,
                "end_line": min(start_line + 25, len(lines)),
                "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                "docstring": ""
            })
        for m in JS_ARROW_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            functions.append({
                "name": m.group(1),
                "type": "arrow_function",
                "start_line": start_line,
                "end_line": min(start_line + 25, len(lines)),
                "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                "docstring": ""
            })
        # Imports
        for m in JS_IMPORT_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            imports.append({
                "module": m.group(3),
                "name": m.group(1) or m.group(2),
                "line": start_line
            })

    elif language == "go":
        for m in GO_TYPE_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            classes.append({
                "name": m.group(1),
                "type": "struct/interface",
                "start_line": start_line,
                "end_line": min(start_line + 30, len(lines)),
                "docstring": "",
                "bases": []
            })
        for m in GO_FUNC_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            functions.append({
                "name": m.group(1),
                "type": "func",
                "start_line": start_line,
                "end_line": min(start_line + 30, len(lines)),
                "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                "docstring": ""
            })

    elif language == "rust":
        for m in RS_STRUCT_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            classes.append({
                "name": m.group(1),
                "type": "struct/enum/trait",
                "start_line": start_line,
                "end_line": min(start_line + 30, len(lines)),
                "docstring": "",
                "bases": []
            })
        for m in RS_FN_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            functions.append({
                "name": m.group(1),
                "type": "fn",
                "start_line": start_line,
                "end_line": min(start_line + 30, len(lines)),
                "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                "docstring": ""
            })
        for m in RS_USE_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            imports.append({
                "module": m.group(1),
                "line": start_line
            })

    elif language in ("java", "c", "cpp"):
        for m in JAVA_CLASS_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            classes.append({
                "name": m.group(1),
                "type": "class",
                "start_line": start_line,
                "end_line": min(start_line + 40, len(lines)),
                "docstring": "",
                "bases": []
            })
        for m in JAVA_METHOD_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            functions.append({
                "name": m.group(1),
                "type": "method",
                "start_line": start_line,
                "end_line": min(start_line + 30, len(lines)),
                "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                "docstring": ""
            })
        for m in CPP_INCLUDE_RE.finditer(source_code):
            start_line = source_code[:m.start()].count("\n") + 1
            imports.append({
                "module": m.group(1),
                "line": start_line
            })

    return {
        "success": True,
        "classes": classes,
        "functions": functions,
        "imports": imports,
        "calls": [],
        "error": None
    }
