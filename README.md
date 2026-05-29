# GSC Tool — codeX RScript Script Extractor & Repacker

Tool untuk membaca, mengedit, dan merepack file script `.gsc` dari Visual Novel **Forest** (Liai Soft), engine **codeX RScript**.

![Proof](https://i.imgur.com/RtR8Go4.png)

---

## Struktur File Game

| File | Isi |
|---|---|
| `scr.xfl` | Archive LB berisi 103 file `.gsc` (semua script game) |
| `grpo.xfl`, `grpo_bg.xfl`, dst. | Archive LB berisi asset grafis (`.wcg`, `.lwg`) |
| `grps.xfl` | Archive LB berisi UI, dialogue image, choice image |

Script yang berisi teks dialog ada di file `.gsc` berukuran besar (±50 KB–400 KB) seperti `2100.gsc`, `2300.gsc`, `2500.gsc`, `2600.gsc`, dst. File `.gsc` kecil (< 5 KB) hanya berisi logic/inisialisasi engine.

---

## Format .gsc

File `.gsc` adalah **bytecode compiled** dari codeX RScript. Strukturnya:

```
[Header 28 bytes]
[Code / Bytecode]
[Offset Table]   ← pointer ke tiap string
[String Table]   ← null-terminated strings (nama variabel & teks dialog)
[Section C]
[Section D]
[Extra trailing]
```

Header terdiri dari 7 × `uint32` little-endian:

| Offset | Field |
|---|---|
| +0x00 | Total size semua seksi |
| +0x04 | Header size (selalu 28) |
| +0x08 | Code size |
| +0x0C | Offset table size |
| +0x10 | String table size |
| +0x14 | Section C size |
| +0x18 | Section D size |

---

## Cara Pakai

### 1. Lihat isi file

```bash
python gsc_tool.py info 2500.gsc
python gsc_tool.py list *.gsc
```

### 2. Export string ke JSON

```bash
python gsc_tool.py export 2500.gsc -o 2500.json
```

### 3. Edit terjemahan di JSON

Buka file JSON, isi field `"translated"` — jangan ubah field lain:

```json
{
  "index": 644,
  "offset": 41002,
  "original": "^ckThe time......t-twelve......",
  "translated": "^ckWaktunya......d-dua belas......"
}
```

> ⚠️ Jangan ubah `"original"`, `"index"`, atau `"offset"`. Hanya isi `"translated"`.  
> Karakter seperti `^ck` adalah **control code** engine — harus ikut disalin/dipertahankan.

### 4. Repack ke .gsc

```bash
python gsc_tool.py import 2500.gsc 2500.json -o 2500_translated.gsc
```

### 5. Batch (semua file sekaligus)

```bash
# Export semua ke folder json/
python gsc_tool.py export-all *.gsc -d json/

# Import semua setelah selesai translate
python gsc_tool.py import-all *.gsc -d json/ -o repacked/
```

### 6. Verifikasi roundtrip

```bash
python gsc_tool.py verify *.gsc
```

Semua 11 file sample telah diverifikasi **100% identik** setelah roundtrip.

---

## Semua Perintah

| Perintah | Fungsi |
|---|---|
| `info <file>` | Detail info + daftar string |
| `info -v <file>` | + hex dump bytecode |
| `list <files...>` | Ringkasan banyak file |
| `export <file> -o out.json` | Export string ke JSON |
| `import <file> <json> -o out.gsc` | Import JSON → repack .gsc |
| `repack <file> -o out.gsc` | Rebuild tanpa edit |
| `verify <files...>` | Cek roundtrip identik |
| `export-all <files...> -d dir/` | Export semua ke folder |
| `import-all <files...> -d dir/ -o dir/` | Import & repack semua |

---

## Catatan

- Default encoding: **Shift-JIS**. Untuk terjemahan non-ASCII (misal Indonesia dengan karakter seperti `é`), gunakan flag `--encoding utf-8` saat import jika engine mendukung.
- String table menyimpan **nama variabel** (`grpo`, `grpo_bg`, dst.) **sekaligus teks dialog** di file `.gsc` besar.
- File `.gsc` kecil (< 5 KB) tidak mengandung dialog, aman diabaikan.
