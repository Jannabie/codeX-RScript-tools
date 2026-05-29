#!/usr/bin/env python3
"""
GSC Tool - Reader & Repacker untuk codeX RScript Visual Novel Engine
Forest VN Script Tool

Format .gsc (codeX RScript bytecode):
  Header (28 bytes / 7 x uint32 LE):
    [0] total_declared_size  = jumlah semua seksi termasuk header
    [1] header_size          = 28 (selalu)
    [2] code_size            = ukuran bytecode
    [3] offset_table_size    = ukuran tabel offset (dalam bytes, tiap entri = 4 bytes)
    [4] string_table_size    = ukuran tabel string (bytes)
    [5] section_c_size       = ukuran seksi C (data tambahan)
    [6] section_d_size       = ukuran seksi D (data tambahan)

  Layout file:
    HEADER         (28 bytes)
    CODE           (code_size bytes)      - bytecode instruksi
    OFFSET_TABLE   (offset_table_size)    - uint32 offsets ke string table
    STRING_TABLE   (string_table_size)    - null-terminated strings
    SECTION_C      (section_c_size)       - data tambahan
    SECTION_D      (section_d_size)       - data tambahan
    EXTRA          (section_d_size bytes) - append di luar header count (untuk file kompleks)
                   (1 byte untuk file sederhana)
"""

import struct
import os
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class GscFile:
    """Representasi parsed dari file .gsc"""
    # Header fields
    header_size: int = 28
    code_size: int = 0
    offset_table_size: int = 0
    string_table_size: int = 0
    section_c_size: int = 0
    section_d_size: int = 0

    # Raw sections (dipertahankan exact)
    code: bytes = b''
    section_c: bytes = b''
    section_d: bytes = b''
    extra: bytes = b''          # bytes di luar total_declared (tidak dihitung di header[0])

    # Parsed string table
    offsets: List[int] = field(default_factory=list)    # offset table entries
    strings: List[str] = field(default_factory=list)    # decoded strings

    # Metadata
    source_path: str = ''

    @property
    def total_declared_size(self) -> int:
        return (self.header_size + self.code_size +
                self.offset_table_size + self.string_table_size +
                self.section_c_size + self.section_d_size)

    def num_offsets(self) -> int:
        return self.offset_table_size // 4


# ─── Reader ───────────────────────────────────────────────────────────────────

def read_gsc(path: str) -> GscFile:
    """Membaca file .gsc dan mem-parse strukturnya."""
    with open(path, 'rb') as f:
        data = f.read()

    if len(data) < 28:
        raise ValueError(f"File terlalu kecil ({len(data)} bytes), minimal 28 bytes untuk header")

    gsc = GscFile(source_path=str(path))

    # Parse header (7 x uint32 LE)
    header = struct.unpack_from('<7I', data, 0)
    total_decl, hdr_sz, code_sz, off_sz, str_sz, sec_c_sz, sec_d_sz = header

    gsc.header_size     = hdr_sz
    gsc.code_size       = code_sz
    gsc.offset_table_size = off_sz
    gsc.string_table_size = str_sz
    gsc.section_c_size  = sec_c_sz
    gsc.section_d_size  = sec_d_sz

    # Hitung posisi tiap seksi
    code_start   = hdr_sz
    off_start    = code_start + code_sz
    str_start    = off_start  + off_sz
    sec_c_start  = str_start  + str_sz
    sec_d_start  = sec_c_start + sec_c_sz
    extra_start  = sec_d_start + sec_d_sz  # = total_decl

    # Validasi
    if extra_start > len(data):
        raise ValueError(
            f"Data korup: total_declared={total_decl} melebihi ukuran file {len(data)}"
        )

    # Ekstrak raw sections
    gsc.code      = data[code_start : off_start]
    gsc.section_c = data[sec_c_start : sec_d_start]
    gsc.section_d = data[sec_d_start : extra_start]
    gsc.extra     = data[extra_start :]  # bytes di luar count (termasuk simple trailing 1-byte)

    # Parse offset table
    num_offsets = off_sz // 4
    gsc.offsets = list(struct.unpack_from(f'<{num_offsets}I', data, off_start))

    # Parse string table
    str_data = data[str_start : str_start + str_sz]
    gsc.strings = _parse_string_table(str_data, gsc.offsets)

    return gsc


def _parse_string_table(str_data: bytes, offsets: List[int]) -> List[str]:
    """Parse string table berdasarkan daftar offset."""
    strings = []
    for off in offsets:
        if off >= len(str_data):
            strings.append('')
            continue
        end = str_data.find(b'\x00', off)
        if end == -1:
            end = len(str_data)
        raw = str_data[off:end]
        # Coba decode: Shift-JIS dulu, fallback UTF-8, fallback latin-1
        for enc in ('shift-jis', 'utf-8', 'latin-1'):
            try:
                strings.append(raw.decode(enc))
                break
            except UnicodeDecodeError:
                continue
        else:
            strings.append(raw.decode('latin-1'))
    return strings


# ─── Writer / Repacker ────────────────────────────────────────────────────────

def build_string_table(strings: List[str], encoding: str = 'shift-jis') -> tuple[bytes, List[int]]:
    """
    Membangun ulang string table dari daftar string.
    Mengembalikan (raw_bytes, offsets_list).
    Setiap entry ditulis sendiri (tanpa dedup) agar struktur offset tetap preserved.
    """
    offsets = []
    table = bytearray()

    for s in strings:
        off = len(table)
        offsets.append(off)
        try:
            encoded = s.encode(encoding)
        except (UnicodeEncodeError, LookupError):
            encoded = s.encode('utf-8')
        table.extend(encoded)
        table.append(0)  # null terminator

    return bytes(table), offsets


def write_gsc(gsc: GscFile, path: str, encoding: str = 'shift-jis'):
    """Menulis ulang (repack) GscFile ke path output."""
    # Rebuild string table dari strings yang (mungkin sudah diedit)
    new_str_data, new_offsets = build_string_table(gsc.strings, encoding)

    # Update sizes
    gsc.string_table_size = len(new_str_data)
    gsc.offset_table_size = len(new_offsets) * 4
    gsc.offsets = new_offsets

    # Susun header
    total = gsc.total_declared_size
    header = struct.pack(
        '<7I',
        total,
        gsc.header_size,
        gsc.code_size,
        gsc.offset_table_size,
        gsc.string_table_size,
        gsc.section_c_size,
        gsc.section_d_size,
    )

    # Susun offset table
    off_table = struct.pack(f'<{len(new_offsets)}I', *new_offsets)

    # Gabungkan semua
    out = (
        header
        + gsc.code
        + off_table
        + new_str_data
        + gsc.section_c
        + gsc.section_d
        + gsc.extra      # bytes di luar total_declared (trailing)
    )

    with open(path, 'wb') as f:
        f.write(out)

    return len(out)


# ─── Info / Display ───────────────────────────────────────────────────────────

def print_info(gsc: GscFile, verbose: bool = False):
    """Mencetak informasi parsed dari GscFile."""
    total = gsc.total_declared_size
    extra_sz = len(gsc.extra)
    file_sz = total + extra_sz

    print(f"=== GSC File: {os.path.basename(gsc.source_path)} ===")
    print(f"  Header size       : {gsc.header_size} bytes")
    print(f"  Code size         : {gsc.code_size} bytes")
    print(f"  Offset table      : {gsc.offset_table_size} bytes ({gsc.num_offsets()} entries)")
    print(f"  String table      : {gsc.string_table_size} bytes")
    print(f"  Section C         : {gsc.section_c_size} bytes")
    print(f"  Section D         : {gsc.section_d_size} bytes")
    print(f"  Extra (trailing)  : {extra_sz} bytes")
    print(f"  Total declared    : {total} bytes")
    print(f"  Total file size   : {file_sz} bytes")
    print()

    if gsc.strings:
        print(f"  String table ({len(gsc.strings)} entries):")
        for i, (off, s) in enumerate(zip(gsc.offsets, gsc.strings)):
            print(f"    [{i:3d}] offset={off:4d}  {repr(s)}")
    else:
        print("  String table: (kosong)")

    if verbose and gsc.code:
        print()
        print(f"  Code hex (first 64 bytes):")
        for i in range(0, min(64, len(gsc.code)), 16):
            chunk = gsc.code[i:i+16]
            hex_str = ' '.join(f'{b:02x}' for b in chunk)
            print(f"    {i:04x}: {hex_str}")


# ─── Export / Import JSON ─────────────────────────────────────────────────────

def export_json(gsc: GscFile, out_path: str):
    """Export string table ke JSON untuk diedit."""
    data = {
        "source_file": os.path.basename(gsc.source_path),
        "encoding": "shift-jis",
        "strings": [
            {
                "index": i,
                "offset": off,
                "original": s,
                "translated": s   # field untuk diisi translator
            }
            for i, (off, s) in enumerate(zip(gsc.offsets, gsc.strings))
        ]
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(gsc.strings)} strings ke: {out_path}")


def import_json(gsc: GscFile, json_path: str) -> GscFile:
    """Import string yang sudah diedit dari JSON ke GscFile."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get('strings', [])
    if len(entries) != len(gsc.strings):
        raise ValueError(
            f"Jumlah string tidak cocok: JSON={len(entries)}, file={len(gsc.strings)}"
        )

    gsc.strings = [e['translated'] for e in entries]
    return gsc


# ─── Batch Operations ─────────────────────────────────────────────────────────

def batch_info(paths: List[str]):
    """Info ringkas untuk banyak file sekaligus."""
    print(f"{'File':<15} {'Size':>6} {'Code':>6} {'Strs':>5} {'OffTab':>7} {'Extra':>6}")
    print("-" * 55)
    for path in paths:
        try:
            gsc = read_gsc(path)
            extra_sz = len(gsc.extra)
            total = gsc.total_declared_size + extra_sz
            print(f"{os.path.basename(path):<15} {total:>6} {gsc.code_size:>6} "
                  f"{len(gsc.strings):>5} {gsc.num_offsets():>7} {extra_sz:>6}")
        except Exception as e:
            print(f"{os.path.basename(path):<15}  ERROR: {e}")


def verify_roundtrip(path: str) -> bool:
    """
    Verifikasi roundtrip: baca -> tulis -> bandingkan dengan asli.
    Mengembalikan True jika identik.
    """
    original = Path(path).read_bytes()
    gsc = read_gsc(path)

    tmp_path = '/tmp/' + os.path.basename(path) + '.verify_tmp'
    write_gsc(gsc, tmp_path)
    result = Path(tmp_path).read_bytes()
    os.remove(tmp_path)

    if original == result:
        return True
    else:
        # Cari perbedaan pertama
        for i, (a, b) in enumerate(zip(original, result)):
            if a != b:
                print(f"  Perbedaan pertama di offset {i} (0x{i:04x}): "
                      f"original=0x{a:02x}, result=0x{b:02x}")
                break
        if len(original) != len(result):
            print(f"  Ukuran berbeda: original={len(original)}, result={len(result)}")
        return False


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='GSC Tool - Reader & Repacker untuk codeX RScript VN Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # Lihat info satu file
  python gsc_tool.py info 0100.gsc

  # Lihat info verbose (termasuk hex dump code)
  python gsc_tool.py info -v 0100.gsc

  # Info ringkas banyak file
  python gsc_tool.py list *.gsc

  # Export string table ke JSON untuk diedit
  python gsc_tool.py export 0100.gsc -o 0100_strings.json

  # Import JSON yang sudah diedit dan repack
  python gsc_tool.py import 0100.gsc 0100_strings.json -o 0100_edited.gsc

  # Repack (tanpa edit, hanya roundtrip rebuild)
  python gsc_tool.py repack 0100.gsc -o 0100_repacked.gsc

  # Verifikasi roundtrip semua file
  python gsc_tool.py verify *.gsc

  # Export semua file ke folder json/
  python gsc_tool.py export-all *.gsc -d json_output/

  # Import dari folder json/ dan output ke folder repacked/
  python gsc_tool.py import-all *.gsc -d json_output/ -o repacked/
        """
    )

    sub = parser.add_subparsers(dest='command', required=True)

    # --- info ---
    p_info = sub.add_parser('info', help='Tampilkan info detail satu file')
    p_info.add_argument('file', help='Path ke file .gsc')
    p_info.add_argument('-v', '--verbose', action='store_true', help='Tampilkan hex dump code')

    # --- list ---
    p_list = sub.add_parser('list', help='Info ringkas banyak file')
    p_list.add_argument('files', nargs='+', help='File .gsc')

    # --- export ---
    p_export = sub.add_parser('export', help='Export string table ke JSON')
    p_export.add_argument('file', help='File .gsc input')
    p_export.add_argument('-o', '--output', help='Output JSON (default: <file>.json)')

    # --- import ---
    p_import = sub.add_parser('import', help='Import JSON dan repack ke .gsc')
    p_import.add_argument('file', help='File .gsc asli (sebagai template)')
    p_import.add_argument('json', help='File JSON yang sudah diedit')
    p_import.add_argument('-o', '--output', help='Output .gsc (default: <file>_edited.gsc)')
    p_import.add_argument('--encoding', default='shift-jis',
                          help='Encoding untuk string (default: shift-jis)')

    # --- repack ---
    p_repack = sub.add_parser('repack', help='Baca dan repack ulang (roundtrip)')
    p_repack.add_argument('file', help='File .gsc input')
    p_repack.add_argument('-o', '--output', help='Output .gsc (default: <file>_repacked.gsc)')

    # --- verify ---
    p_verify = sub.add_parser('verify', help='Verifikasi roundtrip identik dengan asli')
    p_verify.add_argument('files', nargs='+', help='File .gsc')

    # --- export-all ---
    p_ea = sub.add_parser('export-all', help='Export semua file ke folder JSON')
    p_ea.add_argument('files', nargs='+', help='File .gsc')
    p_ea.add_argument('-d', '--dir', default='json_output', help='Folder output JSON')

    # --- import-all ---
    p_ia = sub.add_parser('import-all', help='Import semua JSON dan repack')
    p_ia.add_argument('files', nargs='+', help='File .gsc asli')
    p_ia.add_argument('-d', '--dir', default='json_output', help='Folder berisi JSON')
    p_ia.add_argument('-o', '--output-dir', default='repacked', help='Folder output .gsc')
    p_ia.add_argument('--encoding', default='shift-jis')

    args = parser.parse_args()

    # ── Dispatch ──
    if args.command == 'info':
        gsc = read_gsc(args.file)
        print_info(gsc, verbose=args.verbose)

    elif args.command == 'list':
        batch_info(args.files)

    elif args.command == 'export':
        gsc = read_gsc(args.file)
        out = args.output or (args.file + '.json')
        export_json(gsc, out)

    elif args.command == 'import':
        gsc = read_gsc(args.file)
        gsc = import_json(gsc, args.json)
        out = args.output or (args.file.replace('.gsc', '_edited.gsc'))
        sz = write_gsc(gsc, out, encoding=args.encoding)
        print(f"Repacked {sz} bytes -> {out}")

    elif args.command == 'repack':
        gsc = read_gsc(args.file)
        out = args.output or (args.file.replace('.gsc', '_repacked.gsc'))
        sz = write_gsc(gsc, out)
        print(f"Repacked {sz} bytes -> {out}")

    elif args.command == 'verify':
        all_ok = True
        for path in args.files:
            ok = verify_roundtrip(path)
            status = "✓ OK" if ok else "✗ BEDA"
            print(f"  {status}  {os.path.basename(path)}")
            if not ok:
                all_ok = False
        print()
        print("Semua identik!" if all_ok else "Ada file yang tidak match!")

    elif args.command == 'export-all':
        os.makedirs(args.dir, exist_ok=True)
        for path in args.files:
            gsc = read_gsc(path)
            name = os.path.basename(path)
            out = os.path.join(args.dir, name + '.json')
            export_json(gsc, out)

    elif args.command == 'import-all':
        os.makedirs(args.output_dir, exist_ok=True)
        for path in args.files:
            name = os.path.basename(path)
            json_path = os.path.join(args.dir, name + '.json')
            if not os.path.exists(json_path):
                print(f"  SKIP {name}: tidak ada {json_path}")
                continue
            gsc = read_gsc(path)
            gsc = import_json(gsc, json_path)
            out = os.path.join(args.output_dir, name)
            sz = write_gsc(gsc, out, encoding=args.encoding)
            print(f"  {name} -> {out} ({sz} bytes)")


if __name__ == '__main__':
    main()
