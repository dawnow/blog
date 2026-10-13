import os
chars = set()
for root, _, files in os.walk('public'):
    for f in files:
        if f.endswith('.html'):
            with open(os.path.join(root, f), encoding='utf-8', errors='ignore') as fh:
                chars.update(fh.read())
chars = {c for c in chars if c.isprintable() or c in '\n\t'}
with open('chars.txt', 'w', encoding='utf-8') as fh:
    fh.write(''.join(sorted(chars)))
print(f'{len(chars)} chars -> chars.txt')
