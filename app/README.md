# Kemjar TP Helper

Web app lokal untuk membantu menyiapkan lembar jawaban Tugas Pendahuluan (TP) Praktikum Keamanan
Jaringan (Kemjar): membaca soal, mengisi identitas ke template resmi, mengusulkan referensi format
IEEE lewat Gemini, dan menyusun dokumen `.docx` akhir.

**Jawaban tetap harus ditulis sendiri oleh mahasiswa.** Alat ini hanya membantu tooling
(parsing, formatting, pencarian sumber) — bukan menjawab soal untuk Anda, sesuai ketentuan yang
melarang plagiarisme/AI di soal.

## Setup

```bash
cd app
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` dan isi `GEMINI_API_KEY` dengan API key Gemini milik Anda sendiri
(https://aistudio.google.com/apikey). Field `NAMA`/`NPM`/`KODE_ASLAB`/`TIPE` di `.env` opsional —
hanya untuk prefill form, tetap bisa diubah lewat web app.

## Menjalankan

```bash
uvicorn main:app --reload
```

Buka `http://localhost:8000` di browser.

Untuk diakses dari komputer lain di jaringan yang sama:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Alur pemakaian

1. Isi Nama, NPM, Kode Aslab, No. Modul, Tipe.
2. Upload file soal `.docx` untuk modul tersebut, lalu klik "Baca Soal". Template resmi sudah
   dibundel di `assets/default_template.docx`; upload template sendiri hanya jika Anda punya
   versi lain.
3. Isi jawaban Part 1 (Teori) dan Part 2 (Praktek) di kolom masing-masing. Gemini di sini **tidak**
   memakai pencarian web live (akun free-tier API key umumnya tidak menyertakan kuota Google Search
   grounding) — semua usulan berasal dari pengetahuan model saat training, jadi **bisa saja salah
   atau sudah usang** dan wajib dicek ke sumber aslinya. Untuk Part 1, tombol "Cari Kutipan (AI)"
   mengisi kotak jawaban dengan cuplikan+sumber yang diusulkan AI — **wajib diverifikasi ke sumber
   aslinya lalu ditulis ulang dengan kata Anda sendiri** sebelum submit, bukan jawaban akhir. Centang
   sumber di bawah kotak jawaban yang benar-benar Anda pakai (setelah diverifikasi) agar masuk ke
   daftar Referensi di dokumen akhir. Untuk Part 2, tombol "Cari Langkah (AI)" hanya usulan langkah
   kerja spesifik per tool — verifikasi kredibilitasnya dan jalankan sendiri.
4. Untuk Part 2, upload screenshot yang diminta soal di kolom masing-masing butir.
5. Klik "Generate .docx" untuk mengunduh dokumen akhir dengan identitas terisi, bagian
   Petunjuk/Contoh (merah) sudah dihapus, dan referensi tersusun sesuai gaya template.
6. Buka hasilnya di Word/LibreOffice untuk pengecekan akhir sebelum dikumpulkan (format, margin,
   font, isi) — alat ini tidak menggantikan pengecekan manual.

## Struktur

```
app/
  main.py            FastAPI app & routes
  parser.py          Ekstrak soal Part 1/2/3 dari .docx
  docx_builder.py     Isi identitas & susun jawaban ke template .docx
  gemini_client.py   Usulan referensi & langkah via Gemini (dari pengetahuan model, tanpa pencarian web)
  static/            Frontend (HTML/CSS/vanilla JS)
  assets/            Salinan template resmi bawaan
  .env.example       Contoh konfigurasi (salin ke .env)
```

Semua path relatif terhadap folder `app/` sehingga folder ini bisa disalin ke komputer lain dan
langsung dijalankan tanpa perlu struktur folder `tp/soal` atau `tp/template` di luar `app/`.
