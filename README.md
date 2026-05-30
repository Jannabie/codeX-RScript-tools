# GSC Tool — codeX RScript Script Extractor & Repacker

Tool untuk baca, edit, dan repack file script `.gsc` dari Visual Novel **Forest** (Liar Soft), engine **codeX RScript**.

---

## Proof of Concept

| Screenshot |
|:---:|
| ![Proof](https://i.imgur.com/RtR8Go4.png) |
| *Terjemahan berjalan in-game* |

---

## Struktur File Game

| File | Isi |
|---|---|
| `scr.xfl` | Archive LB berisi 103 file `.gsc` (semua script game) |
| `grpo.xfl`, `grpo_bg.xfl`, dst. | Archive LB berisi asset grafis (`.wcg`, `.lwg`) |
| `grps.xfl` | Archive LB berisi UI, dialogue image, choice image |

File `.gsc` yang berisi dialog biasanya yang ukurannya besar (±50–400 KB) — kayak `2100.gsc`, `2300.gsc`, `2500.gsc`, `2600.gsc`, dsb. Yang ukurannya kecil (< 5 KB) isinya cuma logic/inisialisasi engine, skip aja.

---

## Format .gsc

File `.gsc` adalah **bytecode compiled** dari codeX RScript:

```
[Header 28 bytes]
[Code / Bytecode]
[Offset Table]   ← pointer ke tiap string
[String Table]   ← null-terminated strings (nama variabel & teks dialog)
[Section C]
[Section D]
[Extra trailing]
```

Header: 7 × `uint32` little-endian:

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

### 3. Edit terjemahan

Buka JSON, isi field `"translated"` — jangan ubah yang lain:

```json
{
  "index": 644,
  "offset": 41002,
  "original": "^ckThe time......t-twelve......",
  "translated": "^ckWaktunya......d-dua belas......"
}
```

> ⚠️ Jangan sentuh `"original"`, `"index"`, atau `"offset"`. Karakter kayak `^ck` itu **control code** engine — harus ikut disalin.

### 4. Repack ke .gsc

```bash
python gsc_tool.py import 2500.gsc 2500.json -o 2500_translated.gsc
```

### 5. Batch

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

Semua 11 file sample sudah diverifikasi **100% identik** setelah roundtrip.

---

## Semua Perintah

| Perintah | Fungsi |
|---|---|
| `info <file>` | Detail info + daftar string |
| `info -v <file>` | + hex dump bytecode |
| `list <files...>` | Ringkasan banyak file sekaligus |
| `export <file> -o out.json` | Export string ke JSON |
| `import <file> <json> -o out.gsc` | Import JSON → repack .gsc |
| `repack <file> -o out.gsc` | Rebuild tanpa edit |
| `verify <files...>` | Cek roundtrip identik |
| `export-all <files...> -d dir/` | Export semua ke folder |
| `import-all <files...> -d dir/ -o dir/` | Import & repack semua |

---

## Catatan

- Default encoding: **Shift-JIS**. Kalau terjemahan pakai karakter non-ASCII (misal `é`), tambah flag `--encoding utf-8` saat import — tapi pastiin engine-nya support dulu.
- String table di file `.gsc` besar nyimpen **nama variabel sekaligus teks dialog** — keduanya ada di tempat yang sama.
- File `.gsc` kecil (< 5 KB) nggak ada dialognya, aman diabaikan.
