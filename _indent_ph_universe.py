path = r"c:\Users\Chris Walker\OneDrive\Desktop\Python Coding\streamlit_app.py"
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
# 1-based lines 19148-19401 inclusive -> indices 19147:19401
lo, hi = 19147, 19401
for i in range(lo, min(hi, len(lines))):
    if lines[i].strip():
        lines[i] = "    " + lines[i]
open(path, "w", encoding="utf-8").writelines(lines)
print("done", lo + 1, min(hi, len(lines)))
