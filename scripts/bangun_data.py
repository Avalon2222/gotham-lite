"""
scripts/bangun_data.py - membangun snapshot graf dari data OpenSanctions
========================================================================
Jalankan dengan:   python scripts/bangun_data.py [--sumber FILE] [--keluaran data/]

OpenSanctions menerbitkan seluruh basis datanya sebagai satu berkas JSON Lines dalam format
FollowTheMoney (FtM): satu entitas per baris. Ada dua macam entitas:

- "benda" (Person, Company, Organization, Vessel, ...), dan
- "relasi" (Ownership, Directorship, Family, UnknownLink, ...) yang menunjuk dua benda lewat id.

Skrip ini membaca berkas koleksi ``default`` (±2,5 GB, ±3,9 juta baris) dalam dua lintasan:

1. Lintasan pertama mencatat id semua entitas bertopik sanksi (benih) dan semua relasi yang
   menyentuh benih tersebut.
2. Lintasan kedua menulis simpul (node) untuk benih yang punya relasi dan untuk tetangganya,
   lengkap dengan atribut ringkas: nama, negara, program sanksi, IMO/MMSI kapal, dan sebagainya.

Hasilnya berkas kecil di ``data/`` yang dibaca aplikasi tanpa internet: ``simpul.csv.gz`` dan
``relasi.csv.gz`` (graf), ``dataset.csv`` (judul dataset sumber), ``kapal_tersanksi.csv`` (ringkasan satu
baris per kapal), dan ``META.json`` berisi tanggal dan jumlah.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import pandas as pd
import requests

URL_DEFAULT = "https://data.opensanctions.org/datasets/latest/default/entities.ftm.json"
URL_INDEKS = "https://data.opensanctions.org/datasets/latest/index.json"

# Topik yang menjadikan sebuah entitas "benih" graf. Daftar topik OpenSanctions:
# https://www.opensanctions.org/docs/topics/
TOPIK_BENIH = {"sanction", "sanction.linked", "sanction.counter", "export.control"}

# Skema relasi FtM dan nama properti sumber -> tujuan.
# https://followthemoney.tech/explorer/
RELASI = {
    "Ownership": ("owner", "asset"),
    "Directorship": ("director", "organization"),
    "Membership": ("member", "organization"),
    "Employment": ("employee", "employer"),
    "Family": ("person", "relative"),
    "Associate": ("person", "associate"),
    "Representation": ("agent", "client"),
    "UnknownLink": ("subject", "object"),
}

# Skema benda yang dijadikan simpul. Skema lain (Address, Passport, Sanction, Security) tidak.
TIPE_SIMPUL = {"Person", "Company", "Organization", "LegalEntity", "PublicBody", "Vessel", "Airplane",
               "CryptoWallet", "Asset"}

KOLOM_SIMPUL = ["id", "tipe", "nama", "alias", "negara", "topik", "dataset", "program", "tanggal", "jabatan",
                "imo", "mmsi", "bendera", "jenis_kapal", "tersanksi", "catatan", "url_sumber",
                "pertama_terlihat", "terakhir_berubah"]
KOLOM_RELASI = ["id", "sumber", "tujuan", "tipe", "peran", "mulai", "selesai", "dataset", "persen"]


def _pertama(props: dict, kunci: str, default: str = "") -> str:
    nilai = props.get(kunci) or []
    return str(nilai[0]) if nilai else default


def _gabung(props: dict, kunci: str, maks: int = 6, pemisah: str = "; ") -> str:
    nilai = []
    for v in props.get(kunci) or []:
        v = str(v).strip()
        if v and v not in nilai:
            nilai.append(v)
    return pemisah.join(nilai[:maks])


def _negara(props: dict) -> str:
    """Gabungan unik dari country, jurisdiction, citizenship, nationality, flag (kode ISO 2 huruf)."""
    kode: list[str] = []
    for k in ("country", "jurisdiction", "citizenship", "nationality", "flag"):
        for v in props.get(k) or []:
            v = str(v).lower().strip()
            if v and v not in kode:
                kode.append(v)
    return "; ".join(kode[:6])


def _bersih_imo(nilai: str) -> str:
    nilai = str(nilai).upper().replace("IMO", "").strip()
    return nilai if nilai.isdigit() else ""


def baris_simpul(e: dict) -> dict:
    """Satu entitas FtM (benda) menjadi satu baris CSV ringkas."""
    p = e.get("properties") or {}
    topik = p.get("topics") or []
    nama = e.get("caption") or _pertama(p, "name")
    alias = [a for a in (p.get("alias") or []) + (p.get("name") or []) if a and a != nama]
    alias_unik: list[str] = []
    for a in alias:
        if a not in alias_unik:
            alias_unik.append(a)
    catatan = (_pertama(p, "notes") or _pertama(p, "description") or _pertama(p, "summary"))[:240]
    return {
        "id": e["id"],
        "tipe": e["schema"],
        "nama": nama,
        "alias": "; ".join(alias_unik[:3]),
        "negara": _negara(p),
        "topik": "; ".join(sorted(set(topik))),
        "dataset": "; ".join(e.get("datasets") or []),
        "program": _gabung(p, "programId"),
        "tanggal": _pertama(p, "birthDate") or _pertama(p, "incorporationDate") or _pertama(p, "buildDate"),
        "jabatan": _gabung(p, "position", maks=2),
        "imo": _bersih_imo(_pertama(p, "imoNumber")),
        "mmsi": _pertama(p, "mmsi"),
        "bendera": _pertama(p, "flag").lower(),
        "jenis_kapal": _pertama(p, "type") if e["schema"] == "Vessel" else "",
        "tersanksi": int(any(t in TOPIK_BENIH for t in topik)),
        "catatan": catatan.replace("\n", " "),
        "url_sumber": _pertama(p, "sourceUrl"),
        "pertama_terlihat": (e.get("first_seen") or "")[:10],
        "terakhir_berubah": (e.get("last_change") or "")[:10],
    }


def baris_relasi(e: dict) -> list[dict]:
    """Satu entitas relasi FtM menjadi satu baris per pasangan (sumber, tujuan)."""
    skema = e["schema"]
    if skema not in RELASI:
        return []
    k_sumber, k_tujuan = RELASI[skema]
    p = e.get("properties") or {}
    sumber = p.get(k_sumber) or []
    tujuan = p.get(k_tujuan) or []
    if not sumber or not tujuan:
        return []
    peran = _pertama(p, "role") or _pertama(p, "relationship") or _pertama(p, "summary")
    dataset = (e.get("datasets") or [""])[0]
    hasil = []
    for s in sumber:
        for t in tujuan:
            if s == t:
                continue
            hasil.append({
                "id": e["id"],
                "sumber": s,
                "tujuan": t,
                "tipe": skema,
                "peran": peran[:120],
                "mulai": _pertama(p, "startDate")[:10],
                "selesai": _pertama(p, "endDate")[:10],
                "dataset": dataset,
                "persen": _pertama(p, "percentage"),
            })
    return hasil


def _buka(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def _iter_entitas(path: str, label: str):
    """Membaca JSON Lines baris demi baris; mencetak kemajuan tiap 500 ribu baris."""
    mulai = time.time()
    with _buka(path) as f:
        for i, baris in enumerate(f, 1):
            if i % 500_000 == 0:
                print(f"  [{label}] {i:,} baris, {time.time() - mulai:.0f} dtk", file=sys.stderr)
            baris = baris.strip()
            if baris:
                yield json.loads(baris)


def lintasan_pertama(path: str) -> tuple[dict[str, str], list[dict]]:
    """Kumpulkan id benih (bertopik sanksi) beserta skemanya, dan semua relasi mentah."""
    benih: dict[str, str] = {}
    relasi: list[dict] = []
    for e in _iter_entitas(path, "lintasan 1"):
        skema = e.get("schema")
        if skema in RELASI:
            relasi.extend(baris_relasi(e))
        elif skema in TIPE_SIMPUL:
            topik = (e.get("properties") or {}).get("topics") or []
            if any(t in TOPIK_BENIH for t in topik):
                benih[e["id"]] = skema
    return benih, relasi


# Dataset "ext_*" adalah pengayaan dari register perusahaan (EGRUL Rusia, Companies House, GLEIF, ...).
# Lembaga negara yang disanksi (misalnya kementerian Rusia) tercatat memiliki ribuan badan usaha di
# register itu, dan badan usaha itu saling memiliki lagi; relasi seperti ini membuat graf membengkak
# tanpa menambah cerita. Relasi pengayaan hanya dipertahankan bila salah satu ujungnya orang atau
# kapal yang tersanksi (misalnya oligarki -> perusahaannya, kapal -> pemiliknya).
TIPE_BENIH_PENGAYAAN = {"Person", "Vessel"}
MAKS_TETANGGA_LUAR = 60  # tetangga tidak tersanksi maksimum per simpul tersanksi


def saring_relasi(benih: dict[str, str], relasi: list[dict], maks_tetangga: int = MAKS_TETANGGA_LUAR) -> list[dict]:
    """Simpan relasi yang menyentuh minimal satu benih, dengan tiga aturan pembatas:

    1. duplikat (sumber, tujuan, tipe, peran) dibuang;
    2. relasi dari dataset pengayaan ``ext_*`` dipertahankan hanya bila salah satu ujung
       tersanksinya orang atau kapal;
    3. setiap benih paling banyak menyimpan ``maks_tetangga`` tetangga yang tidak tersanksi
       (relasi antar-benih selalu disimpan).
    """
    terpilih: dict[tuple, dict] = {}
    for r in relasi:
        s_benih, t_benih = r["sumber"] in benih, r["tujuan"] in benih
        if not (s_benih or t_benih):
            continue
        if r["dataset"].startswith("ext_"):
            skema_benih = {benih.get(r["sumber"]), benih.get(r["tujuan"])}
            if not (skema_benih & TIPE_BENIH_PENGAYAAN):
                continue
        kunci = (r["sumber"], r["tujuan"], r["tipe"], r["peran"])
        terpilih.setdefault(kunci, r)

    hasil: list[dict] = []
    hitung_luar: Counter = Counter()
    for kunci in sorted(terpilih):
        r = terpilih[kunci]
        s_benih, t_benih = r["sumber"] in benih, r["tujuan"] in benih
        if s_benih and t_benih:
            hasil.append(r)
            continue
        pemilik = r["sumber"] if s_benih else r["tujuan"]
        if hitung_luar[pemilik] >= maks_tetangga:
            continue
        hitung_luar[pemilik] += 1
        hasil.append(r)
    return hasil


def lintasan_kedua(path: str, dibutuhkan: set[str]) -> list[dict]:
    simpul = []
    for e in _iter_entitas(path, "lintasan 2"):
        if e.get("id") in dibutuhkan and e.get("schema") in TIPE_SIMPUL:
            simpul.append(baris_simpul(e))
    return simpul


def unduh(url: str, tujuan: str) -> str:
    """Mengunduh berkas besar secara streaming ke disk (±2,5 GB, beberapa menit)."""
    print(f"Mengunduh {url} ...", file=sys.stderr)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tujuan, "wb") as f:
            for potongan in r.iter_content(chunk_size=1 << 20):
                f.write(potongan)
    print(f"Selesai: {os.path.getsize(tujuan) / 1e9:.2f} GB", file=sys.stderr)
    return tujuan


def tulis_dataset(df_simpul: pd.DataFrame, df_relasi: pd.DataFrame, keluaran: str, indeks: str | None = None) -> pd.DataFrame:
    """Tabel dataset sumber (judul, penerbit, URL) untuk setiap id dataset yang muncul di graf."""
    dipakai: Counter = Counter()
    # pd.isna: kalau tabel dibaca ulang dari CSV, sel kosong menjadi NaN (dan str(NaN) == "nan").
    for kolom in df_simpul["dataset"]:
        if pd.isna(kolom):
            continue
        for d in str(kolom).split("; "):
            if d:
                dipakai[d] += 1
    for d in df_relasi["dataset"]:
        if not pd.isna(d) and d:
            dipakai[d] += 0
    if indeks:
        with open(indeks, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = requests.get(URL_INDEKS, timeout=120).json()
    info = {d["name"]: d for d in data.get("datasets", [])}
    baris = []
    for nama, jumlah in dipakai.most_common():
        d = info.get(nama, {})
        penerbit = d.get("publisher") or {}
        baris.append({
            "dataset": nama,
            "judul": d.get("title", nama),
            "penerbit": penerbit.get("name", ""),
            "negara_penerbit": penerbit.get("country", ""),
            "url": d.get("url", ""),
            "jumlah_simpul": jumlah,
            "jumlah_relasi": int((df_relasi["dataset"] == nama).sum()),
        })
    df = pd.DataFrame(baris)
    df.to_csv(os.path.join(keluaran, "dataset.csv"), index=False)
    return df


RELASI_PEMILIK = {"Ownership", "Directorship", "Representation", "UnknownLink"}


def tulis_kapal(df_simpul: pd.DataFrame, df_relasi: pd.DataFrame, keluaran: str) -> pd.DataFrame:
    """Tabel ringkas satu baris per kapal tersanksi (CSV biasa, mudah dibaca orang dan aplikasi lain)."""
    nama = dict(zip(df_simpul["id"], df_simpul["nama"]))
    masuk = df_relasi[df_relasi["tipe"].isin(RELASI_PEMILIK)]
    pemilik: dict[str, list[str]] = {}
    for s, t in zip(masuk["sumber"], masuk["tujuan"]):
        daftar = pemilik.setdefault(t, [])
        if nama.get(s) and nama[s] not in daftar:
            daftar.append(nama[s])
    jumlah_relasi = Counter(df_relasi["sumber"].tolist() + df_relasi["tujuan"].tolist())
    kapal = df_simpul[(df_simpul["tipe"] == "Vessel") & (df_simpul["tersanksi"] == 1)].copy()
    kapal["tahun_dibangun"] = pd.to_numeric(kapal["tanggal"].str[:4], errors="coerce").astype("Int64")
    kapal["pemilik"] = [("; ".join(pemilik.get(i, []))[:200]) for i in kapal["id"]]
    kapal["jumlah_relasi"] = [int(jumlah_relasi.get(i, 0)) for i in kapal["id"]]
    kolom = ["id", "nama", "bendera", "jenis_kapal", "imo", "mmsi", "tahun_dibangun", "program", "dataset", "pemilik",
             "jumlah_relasi", "pertama_terlihat"]
    kapal = kapal[kolom].sort_values(["jumlah_relasi", "nama"], ascending=[False, True])
    kapal.to_csv(os.path.join(keluaran, "kapal_tersanksi.csv"), index=False)
    return kapal


def bangun(path: str, keluaran: str, indeks: str | None = None) -> dict:
    benih, relasi_mentah = lintasan_pertama(path)
    print(f"Benih bertopik sanksi: {len(benih):,}; relasi mentah: {len(relasi_mentah):,}", file=sys.stderr)
    relasi = saring_relasi(benih, relasi_mentah)
    del relasi_mentah
    dibutuhkan = {r["sumber"] for r in relasi} | {r["tujuan"] for r in relasi}
    print(f"Relasi terpilih: {len(relasi):,}; simpul dibutuhkan: {len(dibutuhkan):,}", file=sys.stderr)

    simpul = lintasan_kedua(path, dibutuhkan)
    ada = {s["id"] for s in simpul}
    relasi = [r for r in relasi if r["sumber"] in ada and r["tujuan"] in ada]
    print(f"Simpul ditulis: {len(simpul):,}; relasi ditulis: {len(relasi):,}", file=sys.stderr)

    os.makedirs(keluaran, exist_ok=True)
    df_s = pd.DataFrame(simpul, columns=KOLOM_SIMPUL).sort_values(["tipe", "nama"])
    df_r = pd.DataFrame(relasi, columns=KOLOM_RELASI).sort_values(["tipe", "sumber", "tujuan"])
    df_s.to_csv(os.path.join(keluaran, "simpul.csv.gz"), index=False, compression="gzip")
    df_r.to_csv(os.path.join(keluaran, "relasi.csv.gz"), index=False, compression="gzip")
    df_d = tulis_dataset(df_s, df_r, keluaran, indeks)
    df_k = tulis_kapal(df_s, df_r, keluaran)

    meta = {
        "sumber": "OpenSanctions (koleksi default)",
        "url": URL_DEFAULT,
        "dibangun_pada": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "jumlah_simpul": int(len(df_s)),
        "jumlah_relasi": int(len(df_r)),
        "simpul_per_tipe": {k: int(v) for k, v in Counter(df_s["tipe"]).most_common()},
        "relasi_per_tipe": {k: int(v) for k, v in Counter(df_r["tipe"]).most_common()},
        "benih_tersanksi": int(len(benih)),
        "jumlah_dataset": int(len(df_d)),
        "jumlah_kapal_tersanksi": int(len(df_k)),
    }
    with open(os.path.join(keluaran, "META.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(json.dumps(meta, indent=2, ensure_ascii=False), file=sys.stderr)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sumber", help="berkas entities.ftm.json lokal (bila kosong: unduh dari OpenSanctions)")
    ap.add_argument("--indeks", help="berkas index.json lokal (bila kosong: unduh dari OpenSanctions)")
    ap.add_argument("--keluaran", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    args = ap.parse_args()

    path = args.sumber
    if not path:
        path = unduh(URL_DEFAULT, os.path.join(tempfile.gettempdir(), "opensanctions_default.ftm.json"))
    bangun(path, os.path.normpath(args.keluaran), args.indeks)


if __name__ == "__main__":
    main()
