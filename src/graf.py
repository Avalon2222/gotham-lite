"""
src/graf.py - inti analisis keterkaitan (link analysis)
=======================================================
Semua fungsi di sini bekerja pada graf networkx yang dibangun dari data/simpul.csv.gz dan
data/relasi.csv.gz, tanpa Streamlit, sehingga mudah diuji.

Dua bentuk graf dipakai:
- ``MultiDiGraph`` berarah: menyimpan setiap relasi apa adanya (satu pasangan bisa punya dua relasi,
  misalnya "memiliki" sekaligus "mengurus"). Dipakai untuk membaca detail relasi dan arah.
- ``Graph`` tak berarah (``tak_berarah``): dipakai untuk penelusuran (BFS, jalur terpendek, komponen),
  karena untuk pertanyaan "apakah A terhubung ke B" arah tidak penting.
"""

from __future__ import annotations

from collections import Counter, deque

import networkx as nx
import pandas as pd

from .muat_data import LABEL_TIPE, WARNA_TIPE, label_relasi, label_tipe, nama_negara

# Tipe entitas yang diprioritaskan saat sebuah graf harus dipangkas agar tetap terbaca.
PRIORITAS_TIPE = {"Vessel": 0, "Person": 1, "Airplane": 1, "Organization": 2, "Company": 3,
                  "LegalEntity": 3, "PublicBody": 3}


# ----------------------------------------------------------------------------
# 1. MEMBANGUN GRAF
# ----------------------------------------------------------------------------
def bangun_graf(simpul: pd.DataFrame, relasi: pd.DataFrame) -> nx.MultiDiGraph:
    """Graf berarah multi-sisi: simpul = entitas, sisi = relasi FtM.

    Hanya atribut yang sering dipakai saat penelusuran yang disalin ke simpul (tipe, nama, tersanksi);
    atribut lain dibaca dari DataFrame ``simpul`` lewat id agar graf tetap ringan.
    """
    G = nx.MultiDiGraph()
    G.add_nodes_from(
        (i, {"tipe": t, "nama": n, "tersanksi": int(s)})
        for i, t, n, s in zip(simpul["id"], simpul["tipe"], simpul["nama"], simpul["tersanksi"])
    )
    for r in relasi.itertuples(index=False):
        if r.sumber in G and r.tujuan in G:
            G.add_edge(r.sumber, r.tujuan, key=f"{r.id}:{r.sumber}:{r.tujuan}", tipe=r.tipe, peran=r.peran,
                       mulai=r.mulai, selesai=r.selesai, dataset=r.dataset,
                       persen=None if pd.isna(r.persen) else float(r.persen))
    return G


def tak_berarah(G: nx.MultiDiGraph) -> nx.Graph:
    """Versi sederhana tanpa arah dan tanpa sisi ganda, untuk BFS dan jalur terpendek."""
    H = nx.Graph()
    H.add_nodes_from(G.nodes(data=True))
    H.add_edges_from((u, v) for u, v, _ in G.edges(keys=True) if u != v)
    return H


def derajat(H: nx.Graph) -> pd.Series:
    return pd.Series(dict(H.degree()), name="derajat").astype(int)


# ----------------------------------------------------------------------------
# 2. PENCARIAN
# ----------------------------------------------------------------------------
def cari(simpul: pd.DataFrame, teks: str, derajat_simpul: pd.Series | None = None, maks: int = 20,
         tipe: str | None = None) -> pd.DataFrame:
    """Cari entitas berdasarkan nama, alias, IMO, atau MMSI (tidak peka huruf besar/kecil).

    Urutan hasil: nama yang diawali teks pencarian dahulu, lalu yang tersanksi, lalu yang paling
    banyak relasinya. Mengembalikan paling banyak ``maks`` baris.
    """
    q = (teks or "").strip().lower()
    if len(q) < 2:
        return simpul.iloc[0:0]
    nama = simpul["nama"].str.lower()
    alias = simpul["alias"].str.lower()
    cocok = nama.str.contains(q, regex=False) | alias.str.contains(q, regex=False)
    if q.isdigit():
        cocok |= (simpul["imo"] == q) | (simpul["mmsi"] == q)
    hasil = simpul[cocok]
    if tipe:
        hasil = hasil[hasil["tipe"] == tipe]
    if hasil.empty:
        return hasil
    skor_awal = hasil["nama"].str.lower().str.startswith(q).astype(int)
    deg = derajat_simpul.reindex(hasil.index).fillna(0) if derajat_simpul is not None else pd.Series(0, index=hasil.index)
    urut = pd.DataFrame({"awal": skor_awal, "sanksi": hasil["tersanksi"], "deg": deg})
    urutan = urut.sort_values(["awal", "sanksi", "deg"], ascending=[False, False, False]).index
    return hasil.loc[urutan].head(maks)


# ----------------------------------------------------------------------------
# 3. TETANGGA, EGO-GRAF, PERLUASAN
# ----------------------------------------------------------------------------
def tetangga(G: nx.MultiDiGraph, id_: str) -> list[dict]:
    """Semua relasi yang menyentuh satu simpul, satu baris per relasi, lengkap dengan arah.

    ``arah`` = "keluar" bila simpul ini sumber relasi (misalnya ia yang memiliki),
    "masuk" bila ia tujuan (misalnya ia yang dimiliki).
    """
    if id_ not in G:
        return []
    baris = []
    for _, v, d in G.out_edges(id_, data=True):
        baris.append({"id": v, "nama": G.nodes[v]["nama"], "tipe": G.nodes[v]["tipe"],
                      "tersanksi": G.nodes[v]["tersanksi"], "relasi": d["tipe"], "arah": "keluar",
                      "peran": d.get("peran", ""), "dataset": d.get("dataset", ""), "persen": d.get("persen")})
    for u, _, d in G.in_edges(id_, data=True):
        baris.append({"id": u, "nama": G.nodes[u]["nama"], "tipe": G.nodes[u]["tipe"],
                      "tersanksi": G.nodes[u]["tersanksi"], "relasi": d["tipe"], "arah": "masuk",
                      "peran": d.get("peran", ""), "dataset": d.get("dataset", ""), "persen": d.get("persen")})
    baris.sort(key=lambda b: (-b["tersanksi"], PRIORITAS_TIPE.get(b["tipe"], 9), b["nama"]))
    return baris


def _prioritas(H: nx.Graph, n: str) -> tuple:
    d = H.nodes[n]
    return (-d.get("tersanksi", 0), PRIORITAS_TIPE.get(d.get("tipe"), 9), -H.degree(n), n)


def ego(H: nx.Graph, pusat: str, radius: int = 1, maks_simpul: int = 120) -> list[str]:
    """Simpul di sekitar ``pusat`` sampai ``radius`` lompatan, dibatasi ``maks_simpul``.

    Penelusuran melebar (BFS) lapis demi lapis. Bila satu lapis terlalu besar, yang diambil
    diprioritaskan: entitas tersanksi dahulu, lalu kapal/orang, lalu yang paling banyak relasinya.
    Hasil selalu dimulai dengan ``pusat``.
    """
    if pusat not in H:
        return []
    terpilih = [pusat]
    terlihat = {pusat}
    lapis = [pusat]
    for _ in range(radius):
        kandidat = set()
        for n in lapis:
            kandidat.update(v for v in H.neighbors(n) if v not in terlihat)
        if not kandidat:
            break
        sisa = maks_simpul - len(terpilih)
        if sisa <= 0:
            break
        lapis = sorted(kandidat, key=lambda n: _prioritas(H, n))[:sisa]
        terpilih.extend(lapis)
        terlihat.update(lapis)
    return terpilih


def perluas(H: nx.Graph, terpilih: list[str], id_: str, maks_tambahan: int = 40) -> list[str]:
    """Tambahkan tetangga ``id_`` yang belum tampil (paling banyak ``maks_tambahan``) ke daftar simpul."""
    if id_ not in H:
        return list(terpilih)
    ada = set(terpilih)
    baru = sorted((v for v in H.neighbors(id_) if v not in ada), key=lambda n: _prioritas(H, n))[:maks_tambahan]
    return list(terpilih) + baru


def jumlah_tersembunyi(H: nx.Graph, terpilih: list[str]) -> dict[str, int]:
    """Berapa tetangga setiap simpul yang belum ditampilkan (untuk label "+12")."""
    ada = set(terpilih)
    return {n: sum(1 for v in H.neighbors(n) if v not in ada) for n in terpilih if n in H}


# ----------------------------------------------------------------------------
# 4. KONVERSI KE ELEMEN CYTOSCAPE
# ----------------------------------------------------------------------------
def label_gaya(tipe: str, tersanksi: int) -> str:
    """Nama kelompok gaya Cytoscape: 'Person' bila tersanksi, 'Person_luar' bila tidak."""
    return tipe if tersanksi else f"{tipe}_luar"


def teks_relasi(d: dict, maks_peran: int = 60) -> str:
    """'memiliki 51%' / 'mengurus · Director' / 'keluarga dari · spouse'. Peran dipotong pada ``maks_peran`` huruf."""
    teks = label_relasi(d.get("tipe", ""))
    persen = d.get("persen")
    if persen is not None and not pd.isna(persen):
        teks += f" {persen:g}%"
    peran = (d.get("peran") or "").strip()
    if peran and peran.lower() not in teks.lower():
        teks += f" · {peran[:maks_peran]}" + ("…" if len(peran) > maks_peran else "")
    return teks


def elemen_cytoscape(G: nx.MultiDiGraph, simpul: pd.DataFrame, ids: list[str], tersembunyi: dict | None = None,
                     pusat: str | None = None) -> dict:
    """Bentuk {"nodes": [...], "edges": [...]} yang diminta komponen st-link-analysis.

    Hanya sisi yang kedua ujungnya ada di ``ids`` yang dibawa. Sisi ganda antara pasangan yang sama
    tetap ditampilkan satu per satu (Cytoscape menggambarnya melengkung).
    """
    ids = [i for i in ids if i in G]
    ada = set(ids)
    tersembunyi = tersembunyi or {}
    nodes = []
    for i in ids:
        s = simpul.loc[i]
        nama = str(s["nama"])
        sisa = tersembunyi.get(i, 0)
        nodes.append({"data": {
            "id": i,
            "label": label_gaya(s["tipe"], int(s["tersanksi"])),
            "nama": (nama[:38] + "…") if len(nama) > 40 else nama,
            "nama_lengkap": nama,
            "tipe": label_tipe(s["tipe"]),
            "negara": ", ".join(nama_negara(k) for k in str(s["negara"]).split("; ") if k),
            "tersanksi": "ya" if int(s["tersanksi"]) else "tidak",
            "program": str(s["program"]),
            "tetangga_tersembunyi": sisa,
            "pusat": "ya" if i == pusat else "tidak",
        }})
    edges = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if u in ada and v in ada:
            edges.append({"data": {
                "id": k, "source": u, "target": v, "label": d["tipe"],
                "keterangan": teks_relasi(d, maks_peran=24), "dataset": d.get("dataset", ""),
                "mulai": d.get("mulai", ""), "selesai": d.get("selesai", ""),
            }})
    return {"nodes": nodes, "edges": edges}


# ----------------------------------------------------------------------------
# 5. JALUR ANTARA DUA ENTITAS
# ----------------------------------------------------------------------------
def jalur_terpendek(H: nx.Graph, a: str, b: str, maks_jalur: int = 3, maks_panjang: int = 6) -> list[list[str]]:
    """Sampai ``maks_jalur`` jalur sederhana terpendek dari a ke b (panjang <= ``maks_panjang`` sisi)."""
    if a not in H or b not in H or a == b:
        return []
    if not nx.has_path(H, a, b):
        return []
    hasil = []
    for jalur in nx.shortest_simple_paths(H, a, b):
        if len(jalur) - 1 > maks_panjang:
            break
        hasil.append(jalur)
        if len(hasil) >= maks_jalur:
            break
    return hasil


def relasi_antara(G: nx.MultiDiGraph, u: str, v: str) -> list[dict]:
    """Semua relasi langsung antara u dan v, dengan arah yang benar."""
    hasil = []
    if G.has_edge(u, v):
        for d in G.get_edge_data(u, v).values():
            hasil.append({"dari": u, "ke": v, **d})
    if G.has_edge(v, u):
        for d in G.get_edge_data(v, u).values():
            hasil.append({"dari": v, "ke": u, **d})
    return hasil


def ceritakan_jalur(G: nx.MultiDiGraph, jalur: list[str]) -> list[str]:
    """Jalur [A, B, C] -> ['A memiliki B', 'C mengurus B'] dalam kalimat yang bisa dibaca."""
    kalimat = []
    for u, v in zip(jalur, jalur[1:]):
        relasi = relasi_antara(G, u, v)
        if not relasi:
            kalimat.append(f"{G.nodes[u]['nama']} terkait dengan {G.nodes[v]['nama']}")
            continue
        d = relasi[0]
        kalimat.append(f"{G.nodes[d['dari']]['nama']} {teks_relasi(d)} {G.nodes[d['ke']]['nama']}")
    return kalimat


# ----------------------------------------------------------------------------
# 6. KAPAL DAN RANTAI KEPEMILIKAN
# ----------------------------------------------------------------------------
def rantai_pemilik(G: nx.MultiDiGraph, id_: str, maks_hop: int = 4) -> list[list[tuple[str, str]]]:
    """Telusuri ke atas: siapa memiliki/mengurus/mewakili ``id_``, lalu siapa di atasnya lagi.

    Mengembalikan daftar rantai; setiap rantai adalah daftar (id, tipe_relasi) mulai dari pemilik
    langsung. Relasi yang diikuti: Ownership, Directorship, Representation, UnknownLink (arah masuk).
    """
    DIIKUTI = {"Ownership", "Directorship", "Representation", "UnknownLink"}
    rantai: list[list[tuple[str, str]]] = []

    def telusur(n: str, jejak: list[tuple[str, str]], terlihat: set[str]):
        atas = [(u, d["tipe"]) for u, _, d in G.in_edges(n, data=True) if d["tipe"] in DIIKUTI and u not in terlihat]
        if not atas or len(jejak) >= maks_hop:
            if jejak:
                rantai.append(jejak)
            return
        for u, t in sorted(set(atas)):
            telusur(u, jejak + [(u, t)], terlihat | {u})

    if id_ in G:
        telusur(id_, [], {id_})
    return rantai


def tabel_kapal(G: nx.MultiDiGraph, simpul: pd.DataFrame) -> pd.DataFrame:
    """Satu baris per kapal: bendera, IMO, MMSI, jenis, program, pemilik langsung, jumlah relasi."""
    kapal = simpul[simpul["tipe"] == "Vessel"].copy()
    pemilik, jumlah = [], []
    for i in kapal.index:
        atas = [G.nodes[u]["nama"] for u, _, d in G.in_edges(i, data=True)
                if d["tipe"] in ("Ownership", "Directorship", "Representation", "UnknownLink")]
        pemilik.append("; ".join(dict.fromkeys(atas))[:120])
        jumlah.append(G.degree(i) if i in G else 0)
    kapal["pemilik"] = pemilik
    kapal["jumlah_relasi"] = jumlah
    kapal["nama_bendera"] = kapal["bendera"].map(nama_negara)
    return kapal


# ----------------------------------------------------------------------------
# 7. STATISTIK JARINGAN
# ----------------------------------------------------------------------------
def ukuran_komponen(H: nx.Graph) -> list[int]:
    return sorted((len(c) for c in nx.connected_components(H)), reverse=True)


def komponen_dari(H: nx.Graph, id_: str) -> set[str]:
    return nx.node_connected_component(H, id_) if id_ in H else set()


def peringkat_hub(H: nx.Graph, simpul: pd.DataFrame, tipe: str | None = None, n: int = 15,
                  hanya_tersanksi: bool | None = None) -> pd.DataFrame:
    """Simpul dengan relasi terbanyak, bisa disaring per tipe dan status sanksi."""
    deg = derajat(H)
    df = simpul.loc[deg.index, ["nama", "tipe", "negara", "tersanksi", "program"]].copy()
    df["derajat"] = deg.values
    if tipe:
        df = df[df["tipe"] == tipe]
    if hanya_tersanksi is not None:
        df = df[df["tersanksi"] == int(hanya_tersanksi)]
    return df.sort_values("derajat", ascending=False).head(n)


def paparan(H: nx.Graph, simpul: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Entitas yang TIDAK ada di daftar sanksi, diurutkan dari yang paling banyak bertetangga
    dengan entitas tersanksi. Ini pola khas analisis keterkaitan: "belum terdaftar, tetapi dekat".
    """
    baris = []
    for v, d in H.nodes(data=True):
        if d.get("tersanksi"):
            continue
        tetangga_sanksi = sum(1 for u in H.neighbors(v) if H.nodes[u].get("tersanksi"))
        if tetangga_sanksi:
            baris.append((v, d["nama"], d["tipe"], tetangga_sanksi, H.degree(v)))
    df = pd.DataFrame(baris, columns=["id", "nama", "tipe", "tetangga_tersanksi", "derajat"])
    if df.empty:
        return df
    df["negara"] = simpul.loc[df["id"], "negara"].values
    return df.sort_values(["tetangga_tersanksi", "derajat"], ascending=False).head(n).reset_index(drop=True)


def ringkasan(H: nx.Graph, simpul: pd.DataFrame, relasi: pd.DataFrame) -> dict:
    komponen = ukuran_komponen(H)
    deg = derajat(H)
    return {
        "simpul": int(H.number_of_nodes()),
        "relasi": int(len(relasi)),
        "tersanksi": int(simpul["tersanksi"].sum()),
        "tidak_tersanksi": int((simpul["tersanksi"] == 0).sum()),
        "kapal": int((simpul["tipe"] == "Vessel").sum()),
        "orang": int((simpul["tipe"] == "Person").sum()),
        "perusahaan": int(simpul["tipe"].isin(["Company", "Organization", "LegalEntity", "PublicBody"]).sum()),
        "komponen": len(komponen),
        "komponen_terbesar": komponen[0] if komponen else 0,
        "derajat_rata": float(deg.mean()) if len(deg) else 0.0,
        "derajat_median": float(deg.median()) if len(deg) else 0.0,
        "derajat_maks": int(deg.max()) if len(deg) else 0,
    }


def hitung_per_negara(simpul: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Jumlah entitas per negara (satu entitas bisa dihitung di beberapa negara)."""
    c: Counter = Counter()
    for teks in simpul["negara"]:
        for k in str(teks).split("; "):
            if k:
                c[k] += 1
    df = pd.DataFrame(c.most_common(n), columns=["kode", "jumlah"])
    df["negara"] = df["kode"].map(nama_negara)
    return df


def hitung_program(simpul: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    c: Counter = Counter()
    for teks in simpul.loc[simpul["tersanksi"] == 1, "program"]:
        for k in str(teks).split("; "):
            if k:
                c[k] += 1
    return pd.DataFrame(c.most_common(n), columns=["program", "jumlah"])


def hitung_dataset(simpul: pd.DataFrame, judul: dict[str, str], n: int = 15) -> pd.DataFrame:
    c: Counter = Counter()
    for teks in simpul["dataset"]:
        for k in str(teks).split("; "):
            if k:
                c[k] += 1
    df = pd.DataFrame(c.most_common(n), columns=["dataset", "jumlah"])
    df["judul"] = df["dataset"].map(lambda d: judul.get(d, d))
    return df


def distribusi_derajat(H: nx.Graph) -> pd.DataFrame:
    deg = derajat(H)
    kelas = pd.cut(deg, bins=[0, 1, 2, 3, 5, 10, 20, 50, 100, 10_000],
                   labels=["1", "2", "3", "4-5", "6-10", "11-20", "21-50", "51-100", ">100"])
    return kelas.value_counts().sort_index().rename_axis("derajat").reset_index(name="jumlah")


def warna_tipe(tipe: str) -> str:
    return WARNA_TIPE.get(tipe, "#9ca3af")


def label_tipe_semua() -> dict[str, str]:
    return dict(LABEL_TIPE)
