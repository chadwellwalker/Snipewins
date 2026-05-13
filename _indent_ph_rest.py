path = r"c:\Users\Chris Walker\OneDrive\Desktop\Python Coding\streamlit_app.py"
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)

def add4(lo0, hi0_excl):
    for i in range(lo0, min(hi0_excl, len(lines))):
        if lines[i].strip():
            lines[i] = "    " + lines[i]

# 0-based: discover body after "if Discover Players"
add4(19403, 19784)
# my players
add4(19786, 19966)
# buy targets
add4(19968, 19986)

open(path, "w", encoding="utf-8").writelines(lines)
print("ok")
