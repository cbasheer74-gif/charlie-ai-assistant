with open(r'c:\Users\aney\Downloads\Charlie-main-1.0\Charlie-Ai assistant\ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(12235, 12265):
    print(f"{i+1}: {lines[i].rstrip()[:90]}")
