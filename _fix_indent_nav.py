# Fix: script added 12 spaces to Search eBay slice; module-level defs ended up 4 spaces
# shallower than the preceding print(). Add 4 spaces to lines 16888-18912 (1-based).
path = r"c:\Users\Chris Walker\OneDrive\Desktop\Python Coding\streamlit_app.py"
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
lo, hi = 16887, 18912  # 0-based [lo:hi] = lines 16888-18912 inclusive -> slice end 18912 exclusive... hi exclusive
for i in range(lo, min(hi, len(lines))):
    if lines[i].strip():
        lines[i] = "    " + lines[i]
open(path, "w", encoding="utf-8").writelines(lines)
print("patched", lo + 1, "to", min(hi, len(lines)))
