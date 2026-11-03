import ast
from typing import List, Dict, Any, Optional

class PythonASTExtractor(ast.NodeVisitor):
    def __init__(self, source_code: str):
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.classes: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.imports: List[Dict[str, Any]] = []
        self.calls: List[str] = []
        self.current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append({
                "module": alias.name,
                "alias": alias.asname,
                "line": node.lineno
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append({
                "module": f"{module}.{alias.name}" if module else alias.name,
                "base_module": module,
                "name": alias.name,
                "alias": alias.asname,
                "line": node.lineno
            })
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases if hasattr(ast, "unparse")]
        docstring = ast.get_docstring(node) or ""
        end_lineno = getattr(node, "end_lineno", node.lineno)
        
        class_info = {
            "name": node.name,
            "type": "class",
            "start_line": node.lineno,
            "end_line": end_lineno,
            "bases": bases,
            "docstring": docstring.strip() if docstring else "",
            "methods": []
        }
        self.classes.append(class_info)
        
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_function(node, is_async=True)

    def _record_function(self, node, is_async: bool):
        docstring = ast.get_docstring(node) or ""
        end_lineno = getattr(node, "end_lineno", node.lineno)
        
        args = [arg.arg for arg in node.args.args]
        func_info = {
            "name": node.name,
            "type": "method" if self.current_class else "function",
            "parent_class": self.current_class,
            "start_line": node.lineno,
            "end_line": end_lineno,
            "args": args,
            "is_async": is_async,
            "docstring": docstring.strip() if docstring else ""
        }
        
        self.functions.append(func_info)
        if self.current_class and self.classes:
            self.classes[-1]["methods"].append(node.name)
            
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        if func_name and func_name not in self.calls:
            self.calls.append(func_name)
        self.generic_visit(node)

def parse_python_file(source_code: str) -> Dict[str, Any]:
    """Parse python source code into structured symbols, classes, functions, and imports."""
    try:
        tree = ast.parse(source_code)
        extractor = PythonASTExtractor(source_code)
        extractor.visit(tree)
        return {
            "success": True,
            "classes": extractor.classes,
            "functions": extractor.functions,
            "imports": extractor.imports,
            "calls": extractor.calls,
            "error": None
        }
    except SyntaxError as e:
        return {
            "success": False,
            "classes": [],
            "functions": [],
            "imports": [],
            "calls": [],
            "error": f"Syntax error at line {e.lineno}: {e.msg}"
        }
    except Exception as e:
        return {
            "success": False,
            "classes": [],
            "functions": [],
            "imports": [],
            "calls": [],
            "error": str(e)
        }
