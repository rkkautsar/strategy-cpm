# Pine Script v6 Heuristic Static Linter
import sys
import os
import re

def main():
    if len(sys.argv) < 2:
        print("Usage: python pine_lint.py <path_to_pine_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    errors = [] # (line_no, severity, check_name, message, fix)

    # 1. VERSION CHECK
    first_non_blank = None
    first_non_blank_idx = -1
    for idx, l in enumerate(lines):
        if l.strip():
            first_non_blank = l.strip()
            first_non_blank_idx = idx
            break
    
    if first_non_blank != "//@version=6":
        errors.append((
            first_non_blank_idx + 1 if first_non_blank_idx != -1 else 1,
            "LIKELY-ERROR",
            "VERSION",
            f"First non-blank line must be exactly '//@version=6', found: '{first_non_blank}'",
            "Change first line of script to '//@version=6'"
        ))

    # 2. BLOCK COMMENTS
    for idx, l in enumerate(lines):
        if "/*" in l or "*/" in l:
            errors.append((
                idx + 1,
                "LIKELY-ERROR",
                "BLOCK_COMMENTS",
                "Pine Script does not support block comments (/* or */).",
                "Use line comments '//' for each line instead."
            ))

    # Helper to clean lines (replace string literals with spaces, strip line comments)
    clean_lines = []
    for idx, l in enumerate(lines):
        clean_chars = list(l)
        i = 0
        in_double_quote = False
        in_single_quote = False
        while i < len(clean_chars):
            # Check for line comment starting
            if not in_double_quote and not in_single_quote and i < len(clean_chars) - 1 and clean_chars[i] == "/" and clean_chars[i+1] == "/":
                for j in range(i, len(clean_chars)):
                    clean_chars[j] = " "
                break
            
            char = clean_chars[i]
            if char == '"' and not in_single_quote:
                if i > 0 and clean_chars[i-1] == "\\":
                    pass
                else:
                    in_double_quote = not in_double_quote
                    clean_chars[i] = " "
                    i += 1
                    continue
            elif char == "'" and not in_double_quote:
                if i > 0 and clean_chars[i-1] == "\\":
                    pass
                else:
                    in_single_quote = not in_single_quote
                    clean_chars[i] = " "
                    i += 1
                    continue
            
            if in_double_quote or in_single_quote:
                clean_chars[i] = " "
            i += 1
        clean_lines.append("".join(clean_chars))

    # 3. DELIMITER BALANCE (parentheses and brackets)
    whole_file_parens = 0
    whole_file_brackets = 0
    whole_file_braces = 0
    for idx, cl in enumerate(clean_lines):
        for char in cl:
            if char == "(":
                whole_file_parens += 1
            elif char == ")":
                whole_file_parens -= 1
            elif char == "[":
                whole_file_brackets += 1
            elif char == "]":
                whole_file_brackets -= 1
            elif char == "{":
                whole_file_braces += 1
            elif char == "}":
                whole_file_braces -= 1

    if whole_file_parens != 0:
        errors.append((
            0,
            "LIKELY-ERROR",
            "DELIMITER_BALANCE",
            f"Unbalanced parentheses () in file (unmatched count: {abs(whole_file_parens)})",
            "Check all parentheses are correctly closed."
        ))
    if whole_file_brackets != 0:
        errors.append((
            0,
            "LIKELY-ERROR",
            "DELIMITER_BALANCE",
            f"Unbalanced square brackets [] in file (unmatched count: {abs(whole_file_brackets)})",
            "Check all square brackets are correctly closed."
        ))
    if whole_file_braces != 0:
        errors.append((
            0,
            "LIKELY-ERROR",
            "DELIMITER_BALANCE",
            f"Unbalanced curly braces {{}} in file (unmatched count: {abs(whole_file_braces)})",
            "Check all curly braces are correctly closed."
        ))

    # 4. na()-ON-BOOL heuristic
    bool_vars = set()
    assign_pattern = re.compile(r"\b(?:var\s+(?:bool\s+)?)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::?=|=)\s*(.*)")
    for idx, cl in enumerate(clean_lines):
        m = assign_pattern.search(cl)
        if m:
            var_name, expr = m.groups()
            if any(op in expr for op in ["==", "!=", "<", ">", "<=", ">=", " and ", " or ", "not ", "true", "false"]):
                bool_vars.add(var_name)

    # Check for na(var_name)
    na_pattern = re.compile(r"\bna\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)")
    for idx, cl in enumerate(clean_lines):
        for m in na_pattern.finditer(cl):
            var_name = m.group(1)
            if var_name in bool_vars:
                errors.append((
                    idx + 1,
                    "LIKELY-ERROR",
                    "NA_ON_BOOL",
                    f"na({var_name}) called on boolean variable. Pine Script causes a compilation error (CE10123) if na() is called on booleans.",
                    f"Use boolean checks directly (e.g. not {var_name}) or check if initialized differently."
                ))

    # 5. NAMESPACING (v6 requires namespaces for stdev, sqrt, sma, ema, etc.)
    bare_funcs = {
        "stdev": "ta.stdev", "sqrt": "math.sqrt", "sma": "ta.sma", "ema": "ta.ema", 
        "rma": "ta.rma", "atr": "ta.atr", "highest": "ta.highest", "lowest": "ta.lowest",
        "crossover": "ta.crossover", "crossunder": "ta.crossunder", "change": "ta.change",
        "roc": "ta.roc", "tostring": "str.tostring", "abs": "math.abs", "round": "math.round",
        "ceil": "math.ceil", "floor": "math.floor", "max": "math.max", "min": "math.min",
        "pow": "math.pow", "log": "math.log", "log10": "math.log10", "exp": "math.exp",
        "sin": "math.sin", "cos": "math.cos", "tan": "math.tan", "asin": "math.asin",
        "acos": "math.acos", "atan": "math.atan", "sign": "math.sign"
    }
    for idx, cl in enumerate(clean_lines):
        for func, namespaced in bare_funcs.items():
            pattern = re.compile(r"(?<!\.)\b" + func + r"\s*\(")
            if pattern.search(cl):
                errors.append((
                    idx + 1,
                    "LIKELY-ERROR",
                    "NAMESPACING",
                    f"Bare call to '{func}()'. In @version=6, this must be namespaced as '{namespaced}()'.",
                    f"Replace '{func}' with '{namespaced}'"
                ))

    # 6. request.security arg shape
    sec_pattern = re.compile(r"\brequest\.security\s*\(")
    for idx, cl in enumerate(clean_lines):
        if sec_pattern.search(cl):
            start_pos = cl.find("request.security")
            full_call = ""
            for j in range(idx, len(clean_lines)):
                full_call += clean_lines[j] + " "
                open_p = full_call.count("(")
                close_p = full_call.count(")")
                if open_p == close_p and open_p > 0:
                    break
            
            args = []
            current_arg = []
            p_count = 0
            bracket_count = 0
            call_start = full_call.find("request.security") + len("request.security")
            op_idx = full_call.find("(", call_start)
            if op_idx != -1:
                content_to_parse = full_call[op_idx+1:]
                for char in content_to_parse:
                    if char == "(":
                        p_count += 1
                        current_arg.append(char)
                    elif char == ")":
                        p_count -= 1
                        if p_count < 0:
                            args.append("".join(current_arg).strip())
                            break
                        else:
                            current_arg.append(char)
                    elif char == "[":
                        bracket_count += 1
                        current_arg.append(char)
                    elif char == "]":
                        bracket_count -= 1
                        current_arg.append(char)
                    elif char == "," and p_count == 0 and bracket_count == 0:
                        args.append("".join(current_arg).strip())
                        current_arg = []
                    else:
                        current_arg.append(char)
            
            if len(args) < 3:
                errors.append((
                    idx + 1,
                    "LIKELY-ERROR",
                    "SECURITY_ARGS",
                    f"request.security() has too few arguments ({len(args)} found, need at least 3: symbol, timeframe, expression).",
                    "Provide symbol, timeframe, and expression."
                ))

    # 7. USE-BEFORE-ASSIGN heuristic
    assigned_idents = set()
    builtins = {
        "close", "open", "high", "low", "volume", "time", "bar_index",
        "true", "false", "na", "nz", "fixnan",
        "if", "else", "not", "and", "or", "var", "varip", "bool", "float", "int", "string", "color", "table",
        "indicator", "input", "request", "ta", "math", "str", "array", "matrix", "timeframe", "syminfo", "barstate", "ticker",
        "plot", "plotshape", "plotchar", "plotcandle", "bgcolor", "barcolor", "hline", "fill", "alertcondition", "alert",
        "line", "label", "box", "shape", "location", "size", "position", "barmerge",
        "frame_color", "border_width"
    }
    
    # Pass 1: find all declared identifiers (global)
    def_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(([^)]*)\)\s*)?=>")
    var_pattern = re.compile(r"(?:\b(?:var\s+)?(?:bool|float|int|string|color|table)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::?=|=)")
    for cl in clean_lines:
        m_def = def_pattern.search(cl)
        if m_def:
            assigned_idents.add(m_def.group(1))
        m_var = var_pattern.search(cl)
        if m_var:
            assigned_idents.add(m_var.group(1))

    # Pass 2: check for references before declaration/assignment
    currently_assigned = set()
    in_function = False
    func_params = set()
    for idx, cl in enumerate(clean_lines):
        if cl.strip() and (cl.startswith(" ") or cl.startswith("\t")):
            continue
        else:
            in_function = False
            func_params = set()

        m_def = def_pattern.search(cl)
        if m_def:
            in_function = True
            params = m_def.group(2)
            if params:
                for p in params.split(","):
                    func_params.add(p.strip())
            currently_assigned.add(m_def.group(1))
            continue

        words = re.finditer(r"\b[a-zA-Z_][a-zA-Z0-9_.]*\b", cl)
        for m_word in words:
            w = m_word.group(0)
            end_pos = m_word.end()
            # Check if this is a named argument parameter like "gaps=" or "lookahead="
            # If it is followed by '=' (but not '==' or ':='), skip it!
            remainder = cl[end_pos:].lstrip()
            if remainder.startswith("=") and not remainder.startswith("=="):
                continue
                
            root_w = w.split(".")[0]
            if root_w in builtins or root_w in currently_assigned or root_w in func_params:
                continue
            if root_w in ["table", "color", "shape", "location", "size", "position", "barmerge", "barstate", "ta", "math", "str", "request", "input", "color"]:
                continue
            
            m_assign = var_pattern.search(cl)
            if m_assign and m_assign.group(1) == w:
                currently_assigned.add(w)
                continue
                
            if w in assigned_idents:
                errors.append((
                    idx + 1,
                    "LIKELY-ERROR",
                    "USE_BEFORE_ASSIGN",
                    f"Identifier '{w}' referenced before its global declaration/assignment.",
                    f"Move the declaration of '{w}' to before line {idx + 1}."
                ))
            else:
                errors.append((
                    idx + 1,
                    "WARNING",
                    "UNDECLARED",
                    f"Identifier '{w}' is referenced but not declared globally.",
                    f"Check spelling or define '{w}' before use."
                ))
                
        m_var = var_pattern.search(cl)
        if m_var:
            currently_assigned.add(m_var.group(1))

    # 8. var/varip init check
    var_decl_type = {}
    # Better decl regex that handles spaces correctly after types
    decl_pattern = re.compile(r"\b(var\s+|varip\s+)?(?:bool|float|int|string|color|table)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=")
    decl_pattern_simple = re.compile(r"\b(var\s+|varip\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*=")
    for cl in clean_lines:
        if ":=" in cl:
            continue
        m = decl_pattern.search(cl)
        if m:
            is_var = m.group(1) is not None
            var_name = m.group(2)
            var_decl_type[var_name] = "var" if is_var else "regular"
        else:
            m2 = decl_pattern_simple.search(cl)
            if m2:
                is_var = m2.group(1) is not None
                var_name = m2.group(2)
                var_decl_type[var_name] = "var" if is_var else "regular"

    in_block = False
    for idx, cl in enumerate(clean_lines):
        if cl.strip() and (cl.startswith(" ") or cl.startswith("\t")):
            in_block = True
        else:
            in_block = False
            
        if in_block and ":=" in cl:
            m = re.search(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*:=", cl)
            if m:
                v = m.group(1)
                if var_decl_type.get(v) == "regular":
                    errors.append((
                        idx + 1,
                        "WARNING",
                        "PERSISTENCE_RISK",
                        f"Variable '{v}' is re-assigned using ':=' inside a block, but declared using normal '=' instead of 'var'. Its value will reset to the initial value on every bar before the block is evaluated.",
                        f"Declare '{v}' using 'var' or 'varip' if persistence across bars is intended."
                    ))

    # 10. RESERVED/DEPRECATED
    deprecated = {
        "study": "indicator", "security": "request.security", "iff": "ternary operator (?:)",
        "cross": "ta.cross or comparison operators", "input": "input.string/bool/int/float/symbol"
    }
    for idx, cl in enumerate(clean_lines):
        for dep, replacement in deprecated.items():
            pattern = re.compile(r"(?<!\.)\b" + dep + r"\s*\(")
            if pattern.search(cl):
                errors.append((
                    idx + 1,
                    "LIKELY-ERROR",
                    "DEPRECATED",
                    f"Deprecated function '{dep}()' found. In @version=6, use '{replacement}' instead.",
                    f"Replace '{dep}' with '{replacement}'"
                ))

    # 11. Tabs, non-ASCII
    for idx, l in enumerate(lines):
        if "\t" in l:
            errors.append((
                idx + 1,
                "WARNING",
                "TABS",
                "Line contains tab character(s). TradingView recommends spaces for indentation.",
                "Replace tabs with spaces."
            ))
        cl = clean_lines[idx]
        if any(ord(c) > 127 for c in cl):
            errors.append((
                idx + 1,
                "WARNING",
                "NON_ASCII",
                "Line contains non-ASCII characters in active code.",
                "Replace non-ASCII characters with ASCII equivalent."
            ))

    errors = sorted(list(set(errors)), key=lambda x: (x[0], x[1]))

    print(f"=== Pine Script v6 Heuristic Linter Report ===")
    print(f"File: {filepath}\n")
    
    likely_errors = [e for e in errors if e[1] == "LIKELY-ERROR"]
    warnings = [e for e in errors if e[1] == "WARNING"]
    
    print(f"Found {len(likely_errors)} LIKELY-ERRORS and {len(warnings)} WARNINGS.\n")
    
    if likely_errors:
        print("--- LIKELY-ERRORS ---")
        for e in likely_errors:
            line_str = f"Line {e[0]}:" if e[0] > 0 else "File-wide:"
            print(f"[{e[2]}] {line_str} {e[3]}")
            print(f"      Suggested Fix: {e[4]}\n")
            
    if warnings:
        print("--- WARNINGS ---")
        for e in warnings:
            line_str = f"Line {e[0]}:" if e[0] > 0 else "File-wide:"
            print(f"[{e[2]}] {line_str} {e[3]}")
            print(f"      Suggested Fix: {e[4]}\n")
            
    if not errors:
        print("OK: No structural or heuristic issues found.")

if __name__ == "__main__":
    main()
