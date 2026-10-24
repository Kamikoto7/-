"""
Проверяет файлы .py / .go / .js / .ts:
  * todo            — TODO / FIXME / HACK / XXX в комментариях
  * long-line       — слишком длинные строки
  * forbidden-import — запрещённые библиотеки (список в --ban)
  * long-function   — слишком длинные функции (только Python)
  * syntax-error    — синтаксическая ошибка (только Python)
Код проверяемых файлов НЕ запускается. Код выхода: 0 — чисто, 1 — есть находки, 2 — ошибка.
"""
import argparse
import ast
import json
import os
import re
import sys
 
LANGUAGES = {".py": "python", ".go": "go", ".js": "js", ".ts": "js"}  # .ts разбираем как js
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", "vendor"}
COMMENT_MARK = {"python": "#", "go": "//", "js": "//"}
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
IMPORT_RE = {
    "python": re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))"),
    "go": re.compile(r'^\s*(?:import\s+)?(?:[\w.]+\s+)?"([^"]+)"\s*$'),
    "js": re.compile(r"""(?:\bfrom\s*|\brequire\(\s*|^\s*import\s*)['"]([^'"]+)['"]"""),
}
 
 
def is_banned(module, banned):
    """lodash запрещён -> lodash/fp тоже; os запрещён -> os.path тоже."""
    return any(module == b or module.startswith((b + ".", b + "/")) for b in banned)
 
 
def python_functions(text):
    """Возвращает (список (имя, начало, конец), ошибка_синтаксиса или None)."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], (exc.lineno or 1, exc.msg)
    found = [
        (node.name, node.lineno, node.end_lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return found, None
 
 
def check_file(path, rel, lang, args):
    """Проверяет один файл, возвращает (число строк, список находок)."""
    findings = []
 
    def add(line, rule, message):
        findings.append({"file": rel, "line": line, "rule": rule, "message": message})
 
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        add(1, "read-error", f"Не удалось прочитать файл: {exc.strerror}")
        return 0, findings
 
    banned = [b for b in args.ban.split(",") if b]
    mark = COMMENT_MARK[lang]
    for number, line in enumerate(lines, 1):
        if len(line) > args.max_line:
            add(number, "long-line", f"Строка длиннее {args.max_line} символов: {len(line)}")
        _, found_mark, comment = line.partition(mark)  # упрощение: «#» внутри строки тоже считается
        if found_mark and TODO_RE.search(comment):
            add(number, "todo", comment.strip()[:80])
        match = IMPORT_RE[lang].search(line)
        if match and banned:
            module = next(g for g in match.groups() if g)
            if is_banned(module, banned):
                add(number, "forbidden-import", f"Запрещённая библиотека: '{module}'")
 
    if lang == "python":
        functions, error = python_functions("\n".join(lines))
        if error:
            add(error[0], "syntax-error", f"Синтаксическая ошибка: {error[1]}")
        for name, start, end in functions:
            length = end - start + 1
            if length > args.max_func:
                add(start, "long-function", f"Функция '{name}': {length} строк (максимум {args.max_func})")
    return len(lines), findings
 
 
def collect(target):
    """Список (путь, относительный путь, язык) для файла или папки."""
    if os.path.isfile(target):
        lang = LANGUAGES.get(os.path.splitext(target)[1].lower())
        return [(target, os.path.basename(target), lang)] if lang else []
    result = []
    for folder, dirs, names in os.walk(target):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            lang = LANGUAGES.get(os.path.splitext(name)[1].lower())
            if lang:
                full = os.path.join(folder, name)
                result.append((full, os.path.relpath(full, target).replace(os.sep, "/"), lang))
    return result
 
 
def main():
    parser = argparse.ArgumentParser(description="CodeAudit mini: проверка учебного кода")
    parser.add_argument("path", help="папка или файл с кодом")
    parser.add_argument("--max-func", type=int, default=40, help="макс. длина функции (Python), по умолчанию 40")
    parser.add_argument("--max-line", type=int, default=100, help="макс. длина строки, по умолчанию 100")
    parser.add_argument("--ban", default="", help="запрещённые библиотеки через запятую")
    parser.add_argument("--json", action="store_true", help="вывести отчёт в JSON")
    args = parser.parse_args()
 
    if not os.path.exists(args.path):
        print(f"Путь не найден: {args.path}", file=sys.stderr)
        return 2
 
    files = collect(args.path)
    total_lines, findings = 0, []
    for path, rel, lang in files:
        count, found = check_file(path, rel, lang, args)
        total_lines += count
        findings += sorted(found, key=lambda f: f["line"])
 
    if args.json:
        report = {"files": len(files), "lines": total_lines, "findings": findings}
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}  [{f['rule']}]  {f['message']}")
        print(f"\nФайлов: {len(files)}, строк: {total_lines}, находок: {len(findings)}")
    return 1 if findings else 0
 
 
if __name__ == "__main__":
    sys.exit(main())