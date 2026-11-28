"""
src/muat_data.py - membaca snapshot graf dari data/ dan kamus label
====================================================================
Semua berkas di data/ dibuat oleh scripts/bangun_data.py. Modul ini hanya membaca dan merapikan
tipe kolom, serta menyimpan kamus label (tipe entitas, jenis relasi, nama negara) yang dipakai
di seluruh aplikasi agar tampilan konsisten.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import pandas as pd

DIR_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Label tipe entitas FtM -> bahasa Indonesia.
LABEL_TIPE = {
    "Person": "Orang",
    "Company": "Perusahaan",
    "Organization": "Organisasi",
    "LegalEntity": "Badan hukum",
    "PublicBody": "Lembaga publik",
    "Vessel": "Kapal",
    "Airplane": "Pesawat",
    "CryptoWallet": "Dompet kripto",
    "Asset": "Aset",
}

# Warna per tipe (dipakai di graf dan grafik Plotly agar sama).
WARNA_TIPE = {
    "Person": "#fbbf24",
    "Company": "#60a5fa",
    "Organization": "#a78bfa",
    "LegalEntity": "#94a3b8",
    "PublicBody": "#34d399",
    "Vessel": "#22d3ee",
    "Airplane": "#f472b6",
    "CryptoWallet": "#fb923c",
    "Asset": "#9ca3af",
}

# Kata kerja relasi, dibaca dari sumber ke tujuan: "<sumber> <kata kerja> <tujuan>".
LABEL_RELASI = {
    "Ownership": "memiliki",
    "Directorship": "mengurus",
    "Membership": "anggota dari",
    "Employment": "bekerja di",
    "Family": "keluarga dari",
    "Associate": "rekan dari",
    "Representation": "mewakili",
    "UnknownLink": "terkait dengan",
}

WARNA_RELASI = {
    "Ownership": "#fbbf24",
    "Directorship": "#60a5fa",
    "Membership": "#a78bfa",
    "Employment": "#a78bfa",
    "Family": "#f472b6",
    "Associate": "#f472b6",
    "Representation": "#34d399",
    "UnknownLink": "#6b7280",
}

# Kode ISO-2 -> nama negara (yang sering muncul di data sanksi). Kode lain ditampilkan apa adanya.
NAMA_NEGARA = {
    "ru": "Rusia", "ua": "Ukraina", "by": "Belarus", "kp": "Korea Utara", "kr": "Korea Selatan",
    "ir": "Iran", "iq": "Irak", "sy": "Suriah", "ye": "Yaman", "lb": "Lebanon", "il": "Israel", "ps": "Palestina",
    "cn": "Tiongkok", "hk": "Hong Kong", "tw": "Taiwan", "mo": "Makau", "jp": "Jepang", "mn": "Mongolia",
    "us": "Amerika Serikat", "gb": "Inggris", "eu": "Uni Eropa", "de": "Jerman", "fr": "Prancis", "it": "Italia",
    "es": "Spanyol", "nl": "Belanda", "be": "Belgia", "ch": "Swiss", "at": "Austria", "se": "Swedia", "no": "Norwegia",
    "fi": "Finlandia", "dk": "Denmark", "pl": "Polandia", "cz": "Ceko", "sk": "Slowakia", "hu": "Hungaria",
    "ro": "Rumania", "bg": "Bulgaria", "gr": "Yunani", "cy": "Siprus", "mt": "Malta", "pt": "Portugal",
    "ie": "Irlandia", "lu": "Luksemburg", "lv": "Latvia", "lt": "Lituania", "ee": "Estonia", "md": "Moldova",
    "ge": "Georgia", "am": "Armenia", "az": "Azerbaijan", "kz": "Kazakhstan", "uz": "Uzbekistan", "kg": "Kirgizstan",
    "tj": "Tajikistan", "tm": "Turkmenistan", "tr": "Turki", "rs": "Serbia", "ba": "Bosnia-Herzegovina",
    "me": "Montenegro", "mk": "Makedonia Utara", "al": "Albania", "xk": "Kosovo", "hr": "Kroasia", "si": "Slovenia",
    "ae": "Uni Emirat Arab", "sa": "Arab Saudi", "qa": "Qatar", "kw": "Kuwait", "om": "Oman", "bh": "Bahrain",
    "jo": "Yordania", "eg": "Mesir", "ly": "Libya", "tn": "Tunisia", "dz": "Aljazair", "ma": "Maroko", "sd": "Sudan",
    "ss": "Sudan Selatan", "so": "Somalia", "et": "Ethiopia", "er": "Eritrea", "dj": "Djibouti", "ke": "Kenya",
    "tz": "Tanzania", "ug": "Uganda", "rw": "Rwanda", "cd": "Kongo (DRC)", "cg": "Kongo", "cf": "Afrika Tengah",
    "cm": "Kamerun", "ng": "Nigeria", "ne": "Niger", "ml": "Mali", "bf": "Burkina Faso", "gn": "Guinea",
    "gw": "Guinea-Bissau", "sl": "Sierra Leone", "lr": "Liberia", "ci": "Pantai Gading", "gh": "Ghana", "tg": "Togo",
    "bj": "Benin", "sn": "Senegal", "gm": "Gambia", "mr": "Mauritania", "td": "Chad", "ga": "Gabon", "ao": "Angola",
    "zw": "Zimbabwe", "zm": "Zambia", "mz": "Mozambik", "mg": "Madagaskar", "za": "Afrika Selatan", "km": "Komoro",
    "sc": "Seychelles", "mu": "Mauritius", "in": "India", "pk": "Pakistan", "af": "Afganistan", "bd": "Bangladesh",
    "lk": "Sri Lanka", "np": "Nepal", "mv": "Maladewa", "mm": "Myanmar", "th": "Thailand", "la": "Laos",
    "kh": "Kamboja", "vn": "Vietnam", "my": "Malaysia", "sg": "Singapura", "id": "Indonesia", "ph": "Filipina",
    "bn": "Brunei", "tl": "Timor-Leste", "au": "Australia", "nz": "Selandia Baru", "pg": "Papua Nugini", "fj": "Fiji",
    "vu": "Vanuatu", "ws": "Samoa", "to": "Tonga", "ki": "Kiribati", "pw": "Palau", "mh": "Kepulauan Marshall",
    "fm": "Mikronesia", "tv": "Tuvalu", "ck": "Kepulauan Cook", "ca": "Kanada", "mx": "Meksiko", "cu": "Kuba",
    "ve": "Venezuela", "co": "Kolombia", "br": "Brasil", "ar": "Argentina", "cl": "Chili", "pe": "Peru",
    "ec": "Ekuador", "bo": "Bolivia", "py": "Paraguay", "uy": "Uruguay", "ni": "Nikaragua", "hn": "Honduras",
    "gt": "Guatemala", "sv": "El Salvador", "pa": "Panama", "cr": "Kosta Rika", "do": "Republik Dominika",
    "ht": "Haiti", "bs": "Bahama", "bb": "Barbados", "bz": "Belize", "jm": "Jamaika", "tt": "Trinidad dan Tobago",
    "dm": "Dominika", "ag": "Antigua dan Barbuda", "kn": "Saint Kitts dan Nevis", "lc": "Saint Lucia",
    "vc": "Saint Vincent", "gd": "Grenada", "vg": "Kepulauan Virgin Britania", "ky": "Kepulauan Cayman",
    "bm": "Bermuda", "gi": "Gibraltar", "je": "Jersey", "gg": "Guernsey", "im": "Isle of Man", "li": "Liechtenstein",
    "mc": "Monako", "sm": "San Marino", "fo": "Kepulauan Faroe", "ad": "Andorra", "va": "Vatikan", "is": "Islandia", "cw": "Curaçao",
    "sx": "Sint Maarten", "aw": "Aruba", "st": "São Tomé", "cv": "Tanjung Verde", "gq": "Guinea Khatulistiwa",
    "suhh": "Uni Soviet (lama)", "zz": "Internasional", "xx": "Tidak diketahui", "csxx": "Cekoslowakia (lama)",
    "yucs": "Yugoslavia (lama)", "ddde": "Jerman Timur (lama)",
    # Kode yang muncul di data OpenSanctions tetapi belum punya nama (dulu tampil sebagai "GY", "UA-DPR").
    "gy": "Guyana", "sr": "Suriname", "sz": "Eswatini", "na": "Namibia", "bw": "Botswana", "bi": "Burundi",
    "pr": "Puerto Riko", "io": "Wilayah Samudra Hindia Britania", "zr": "Zaire (lama)",
    "cshh": "Cekoslowakia (lama)", "dd": "Jerman Timur (lama)", "gb-sct": "Skotlandia",
    "ua-cri": "Krimea", "ua-dpr": "Donetsk (wilayah pendudukan)", "ua-lpr": "Luhansk (wilayah pendudukan)",
    "md-pmr": "Transnistria", "x-so": "Somaliland",
}

# Bendera kemudahan (flag of convenience) menurut daftar ITF; dipakai di tab armada.
BENDERA_KEMUDAHAN = {"pa", "lr", "mh", "mt", "bs", "ag", "cy", "km", "kh", "vu", "pw", "sl", "tg", "tz", "ga",
                     "gm", "cm", "bb", "bz", "bm", "ky", "vc", "lb", "mn", "md", "ws", "to", "cw", "gq", "hn", "jm",
                     "kn", "lk", "mu", "sm", "st", "tv", "ck", "gi", "fo", "bo", "ki", "fm", "ni"}


def nama_negara(kode: str) -> str:
    """'ru' -> 'Rusia'; kode yang tidak dikenal dikembalikan dalam huruf besar."""
    kode = kode.strip().lower() if isinstance(kode, str) else ""  # NaN/None -> kosong
    if not kode:
        return ""
    return NAMA_NEGARA.get(kode, kode.upper())


def daftar_negara(teks: str, maks: int | None = None) -> list[str]:
    """'ru; cy' -> ['Rusia', 'Siprus']. Pemisah tanpa spasi ('ru;cy') juga diterima.

    ``maks`` membatasi jumlah negara yang dikembalikan (setelah kode ganda dibuang).
    """
    if not isinstance(teks, str):
        return []
    # Kode yang sama bisa muncul dua kali ("ru; RU") saat sumber digabung; tampilkan sekali saja.
    hasil: list[str] = []
    for k in teks.split(";"):
        if k.strip():
            nama = nama_negara(k)
            if nama not in hasil:
                hasil.append(nama)
    return hasil if maks is None else hasil[:max(maks, 0)]


def label_tipe(tipe: str) -> str:
    return LABEL_TIPE.get(tipe, tipe)


def label_relasi(tipe: str) -> str:
    return LABEL_RELASI.get(tipe, "terkait dengan")


@dataclass
class DataGraf:
    simpul: pd.DataFrame      # satu baris per entitas, index = id
    relasi: pd.DataFrame      # satu baris per relasi
    dataset: pd.DataFrame     # keterangan dataset sumber
    meta: dict


def muat_simpul(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(DIR_DATA, "simpul.csv.gz")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    # Sel kosong ("" karena keep_default_na=False) dianggap tidak tersanksi, bukan ValueError.
    # Isinya dirapikan jadi 0/1: "True" dari ekspor lain dulu terbaca 0 (tidak tersanksi), "inf" membuat
    # astype(int) gagal, dan "1.0" atau "2" tidak ikut dihitung di bagian yang memakai tersanksi == 1.
    teks = df["tersanksi"].str.strip().str.lower()
    angka = pd.to_numeric(teks, errors="coerce").fillna(0)
    df["tersanksi"] = ((angka != 0) | teks.isin(["true", "ya", "yes"])).astype(int)
    df["nama"] = df["nama"].str.strip().replace("", "(tanpa nama)")
    df["tahun"] = pd.to_numeric(df["tanggal"].str[:4], errors="coerce").astype("Int64")
    # id berspasi tidak cocok dengan sumber/tujuan relasi, dan id kosong bukan entitas.
    df["id"] = df["id"].str.strip()
    df = df[df["id"] != ""]
    # id ganda membuat simpul.loc[id] berupa DataFrame (bukan satu baris) dan elemen graf gagal dibentuk.
    df = df.drop_duplicates("id", keep="first")
    return df.set_index("id", drop=False)


def muat_relasi(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(DIR_DATA, "relasi.csv.gz")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    # Persen dari sumber lain kadang ditulis "51%" atau "12,5"; dulu keduanya hilang jadi kosong.
    teks = df["persen"].str.strip().str.rstrip("%").str.strip().str.replace(",", ".", regex=False)
    persen = pd.to_numeric(teks, errors="coerce")
    # Persen di luar 0-100 (mis. "-5" atau "1500", salah ketik di sumber) bukan porsi kepemilikan;
    # dulu ikut tampil sebagai "1500%" di label relasi.
    df["persen"] = persen.where((persen >= 0) & (persen <= 100))
    # Sama seperti id simpul: sumber/tujuan berspasi membuat relasinya diam-diam tidak masuk graf.
    for kolom in ("sumber", "tujuan"):
        df[kolom] = df[kolom].str.strip()
    # Relasi tanpa salah satu ujung tidak bisa digambar, dan relasi ke diri sendiri hanya menambah
    # lingkaran di graf tanpa informasi.
    df = df[(df["sumber"] != "") & (df["tujuan"] != "") & (df["sumber"] != df["tujuan"])]
    return df.reset_index(drop=True)


def muat_dataset(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(DIR_DATA, "dataset.csv")
    return pd.read_csv(path, dtype={"dataset": str, "judul": str, "penerbit": str, "negara_penerbit": str,
                                    "url": str}, keep_default_na=False)


def muat_meta(path: str | None = None) -> dict:
    path = path or os.path.join(DIR_DATA, "META.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def muat_semua(direktori: str | None = None) -> DataGraf:
    d = direktori or DIR_DATA
    return DataGraf(
        simpul=muat_simpul(os.path.join(d, "simpul.csv.gz")),
        relasi=muat_relasi(os.path.join(d, "relasi.csv.gz")),
        dataset=muat_dataset(os.path.join(d, "dataset.csv")),
        meta=muat_meta(os.path.join(d, "META.json")),
    )


def judul_dataset(df_dataset: pd.DataFrame) -> dict[str, str]:
    """id dataset -> judul, misalnya 'us_ofac_sdn' -> 'US OFAC Specially Designated Nationals (SDN) List'."""
    return dict(zip(df_dataset["dataset"], df_dataset["judul"]))


def url_opensanctions(id_entitas: str) -> str:
    return f"https://www.opensanctions.org/entities/{id_entitas}/"
