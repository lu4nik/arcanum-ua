#!/usr/bin/env python3
"""Minimal Troika DAT reader (Arcanum). List / extract / stat text files."""
import struct, sys, zlib, os, fnmatch

FLAG_COMPRESSED = 0x002  # guess; verify by sizes
FLAG_DIR = 0x400         # guess; dirs have size 0 anyway

def read_entries(path):
    with open(path, 'rb') as f:
        f.seek(-12, 2)
        tag, name_table_size = struct.unpack('<4si', f.read(8))
        if tag == b' TAD':
            pass
        elif tag == b'1TAD':
            f.seek(-24, 2)
            f.read(16)  # guid
            tag2 = f.read(4)
        else:
            # try DAT1 layout anyway
            f.seek(-24, 2)
            guid = f.read(16)
            tag2, name_table_size = struct.unpack('<4si', f.read(8))
            if tag2 != b'1TAD':
                raise ValueError(f'{path}: not a Troika DAT (tag={tag!r})')
        (entry_table_offset,) = struct.unpack('<i', f.read(4))
        f.seek(-4 - entry_table_offset, 2)
        (entry_table_size,) = struct.unpack('<i', f.read(4))
        pos = f.tell()
        f.seek(0, 2)
        size = f.tell()
        f.seek(pos)
        base = size - entry_table_size - entry_table_offset
        (count,) = struct.unpack('<i', f.read(4))
        entries = []
        for _ in range(count):
            (name_size,) = struct.unpack('<i', f.read(4))
            name = f.read(name_size).rstrip(b'\x00').decode('cp1252', 'replace')
            f.read(4)  # unknown
            flags, usize, csize, offset = struct.unpack('<4i', f.read(16))
            entries.append((name.replace('\\', '/').lower(), flags, usize, csize, offset + base))
        return entries

def read_file(path, entry):
    name, flags, usize, csize, offset = entry
    with open(path, 'rb') as f:
        f.seek(offset)
        if flags & 0x002:
            return zlib.decompress(f.read(csize))
        return f.read(usize)

if __name__ == '__main__':
    cmd, dat = sys.argv[1], sys.argv[2]
    entries = read_entries(dat)
    if cmd == 'list':
        pat = sys.argv[3] if len(sys.argv) > 3 else '*'
        for e in entries:
            if fnmatch.fnmatch(e[0], pat):
                print(f'{e[2]:>10} {e[0]}')
    elif cmd == 'stat':
        # count files/bytes by extension
        from collections import Counter
        cnt, byt = Counter(), Counter()
        for e in entries:
            ext = os.path.splitext(e[0])[1] or '(dir)'
            cnt[ext] += 1
            byt[ext] += e[2]
        for ext, n in cnt.most_common(30):
            print(f'{ext:12} {n:>7} files {byt[ext]:>12} bytes')
    elif cmd == 'cat':
        pat = sys.argv[3]
        for e in entries:
            if fnmatch.fnmatch(e[0], pat):
                sys.stdout.buffer.write(read_file(dat, e))
                break
    elif cmd == 'textstat':
        # lines & words across all .mes/.dlg files
        pat = sys.argv[3] if len(sys.argv) > 3 else '*'
        files = lines = words = chars = 0
        for e in entries:
            if fnmatch.fnmatch(e[0], pat) and e[2] > 0:
                try:
                    data = read_file(dat, e).decode('cp1252', 'replace')
                except Exception:
                    continue
                files += 1
                lines += data.count('\n')
                words += len(data.split())
                chars += len(data)
        print(f'{pat}: {files} files, {lines} lines, {words} words, {chars} chars')
