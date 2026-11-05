"""
app.py - Gotham Lite
====================
Jalankan dengan:   streamlit run app.py

Alur besar file ini (baca dari atas ke bawah):
  1. Import library + konfigurasi halaman
  2. Muat snapshot graf OpenSanctions (src/muat_data.py) dan bangun graf networkx (src/graf.py)
  3. Sidebar: pencarian entitas, kasus siap pakai, pengaturan graf, learning mode
  4. Ringkasan angka
  5. Tab: explorer -> connections -> shadow fleet -> network stats -> data -> cara kerja

Logika yang bisa diuji ada di src/ (graf, pencarian, jalur, AIS); file ini hanya menyusun UI.
Setiap bagian diberi komentar "APA" dan "MENGAPA". Penjelasan istilah ada di docs/BELAJAR.md.
"""

from __future__ import annotations

import base64
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from st_link_analysis import EdgeStyle, Event, NodeStyle, st_link_analysis

from src import ais, graf, muat_data
from src.muat_data import LABEL_TIPE, WARNA_RELASI, WARNA_TIPE, label_relasi, label_tipe, nama_negara

# ----------------------------------------------------------------------------
# 0. KONFIGURASI HALAMAN
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Gotham Lite", page_icon="🕸️", layout="wide")

# Kunci API aisstream.io (opsional, hanya untuk tab Live AIS) dibaca dari st.secrets atau env.
try:
    _kunci = st.secrets.get("aisstream", {}).get("api_key")
    if _kunci:
        os.environ["AISSTREAM_API_KEY"] = str(_kunci).strip()  # selalu ikuti Secrets terbaru, bukan nilai lama
except Exception:  # tidak ada berkas secrets
    pass

TEMPLATE = "plotly_dark"
EMAS = "#fbbf24"
BIRU = "#60a5fa"
ABU = "#5b6b82"
MERAH = "#ff2d55"
DISCLAIMER = (
    "ℹ️ Seluruh entitas dan relasi berasal dari **OpenSanctions**, agregator terbuka atas daftar sanksi dan "
    "daftar pengawasan resmi (OFAC, Uni Eropa, Inggris, PBB, Ukraina, dan lain-lain) beserta pengayaan dari "
    "register perusahaan publik. Keberadaan sebuah nama di graf ini **bukan** bukti pelanggaran; entitas yang "
    "tidak tersanksi tampil semata karena punya relasi tercatat dengan entitas tersanksi. Proyek ini edukatif "
    "dan portofolio pribadi, bukan alat kepatuhan."
)

# Ikon per tipe. Nama ikon Material tersedia di st-link-analysis; kapal memakai SVG sendiri.
_SVG_KAPAL = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24' fill='%s'>"
    "<path d='M20 21c-1.4 0-2.7-.5-3.8-1.3-2.3 1.7-5.1 1.7-7.4 0C7.7 20.5 6.4 21 5 21H3v-2h2c1.4 0 2.6-.6 3.6-1.6l.4-.4.4.4c2 2 5.2 2 7.2 0l.4-.4.4.4c1 1 2.2 1.6 3.6 1.6h2v2h-2zM3.9 17.9 2 11.4l1.9-.6L5 14.3V6h4V3h6v3h4v8.3l1.1-3.5 1.9.6-1.9 6.5c-1-.3-1.8-.9-2.5-1.6-2.2 2.1-5 2.1-7.2 0-.7.7-1.5 1.3-2.5 1.6zM7 8v4.9c1.6-.6 3.3-.6 5-.1 1.7-.5 3.4-.5 5 .1V8H7z'/></svg>"
)


def ikon_tipe(tipe: str, warna: str = "#0b0e14") -> str:
    if tipe == "Vessel":
        return "url(data:image/svg+xml;base64," + base64.b64encode((_SVG_KAPAL % warna).encode()).decode() + ")"
    return {"Person": "person", "Company": "business", "Organization": "group", "LegalEntity": "account_balance",
            "PublicBody": "assured_workload", "Airplane": "flight", "CryptoWallet": "wallet"}.get(tipe, "inventory")


def redup(hex_: str, faktor: float = 0.45) -> str:
    """Versi lebih gelap dari sebuah warna heksadesimal (untuk entitas yang tidak tersanksi)."""
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * faktor), int(g * faktor), int(b * faktor))


class GayaSimpul(NodeStyle):
    """NodeStyle bawaan memakai huruf 3,6 px (tidak terbaca); kelas ini menambah ukuran huruf, warna teks, dan ukuran simpul."""

    def dump(self):
        d = super().dump()
        d["style"].update({"font-size": 8, "min-zoomed-font-size": 4, "color": "#e6edf3", "text-wrap": "ellipsis",
                           "text-max-width": 95, "width": 24, "height": 24, "text-margin-y": 4,
                           "text-outline-color": "#0b0e14", "text-outline-width": 1.5, "border-width": 1.2,
                           "border-color": "#0b0e14"})
        return d


class GayaRelasi(EdgeStyle):
    def dump(self):
        d = super().dump()
        d["style"].update({"font-size": 5.5, "min-zoomed-font-size": 5, "color": "#c9d1d9", "text-rotation": "autorotate", "width": 1.2,
                           "text-background-opacity": 0, "text-outline-color": "#0b0e14", "text-outline-width": 1,
                           "arrow-scale": 0.7})
        return d


GAYA_SIMPUL = []
for _t, _w in WARNA_TIPE.items():
    GAYA_SIMPUL.append(GayaSimpul(_t, _w, "nama", ikon_tipe(_t)))
    GAYA_SIMPUL.append(GayaSimpul(f"{_t}_luar", redup(_w), "nama", ikon_tipe(_t, "#c9d1d9")))
GAYA_RELASI = [GayaRelasi(t, w, caption="keterangan", directed=True) for t, w in WARNA_RELASI.items()]
GAYA_RELASI_POLOS = [GayaRelasi(t, w, directed=True) for t, w in WARNA_RELASI.items()]
TATA_LETAK = {"Organik (fcose)": "fcose", "Melingkar": "concentric", "Hierarki": "breadthfirst", "Cose": "cose"}

# Kasus siap pakai: dicari lewat nama saat aplikasi berjalan, agar tetap bekerja walau id berubah
# setelah data diperbarui.
KASUS = [
    ("🇮🇷 Armada bayangan Iran", "Mohammad Hossein Shamkhani", "Person",
     "Putra penasihat Pemimpin Tertinggi Iran; OFAC memetakan puluhan tanker dan perusahaan cangkang di sekitarnya."),
    ("🇰🇵 Kapal Chong Chon Gang", "Chong Chon Gang", "Vessel",
     "Kapal Korea Utara yang tertangkap membawa senjata Kuba (2013); laporan RUSI mencatat awak, operator, dan pemiliknya."),
    ("🇷🇺 Jaringan Prigozhin", "Yevgeny Prigozhin", "Person",
     "Pendiri Wagner; perusahaan katering, media, dan tambang yang terhubung kepadanya."),
    ("🇾🇪 Jaringan Al-Jamal (Houthi)", "Sa'id Ahmad Muhammad Al-Jamal", "Person",
     "Pemodal Houthi berbasis Iran; jaringan kapal dan perusahaan pengiriman minyaknya."),
    ("🇷🇺 Keluarga Rotenberg", "Arkady Romanovich Rotenberg", "Person",
     "Sahabat masa kecil Putin; saudara, anak, dan puluhan perusahaan."),
    ("🇷🇺 Usmanov & keluarga", "Alisher Usmanov", "Person",
     "Oligarki yang asetnya banyak dialihkan ke kerabat; relasi keluarga dari Wikidata."),
]


def rapikan(fig: go.Figure, tinggi: int = 400) -> go.Figure:
    """Gaya seragam untuk semua grafik Plotly: latar gelap, grid tipis, legenda di atas."""
    fig.update_layout(
        template=TEMPLATE, height=tinggi, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=20, t=60, b=10),
        title=dict(y=0.98, yanchor="top", x=0, xanchor="left", font=dict(size=15)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, title=None)
    fig.update_yaxes(gridcolor="#243044", zeroline=False, title=None)
    return fig


def angka(n) -> str:
    """1234 -> '1.234' (format Indonesia)."""
    return f"{int(n):,}".replace(",", ".")


# ----------------------------------------------------------------------------
# 1. MUAT DATA + BANGUN GRAF (sekali per proses, dibagi semua pengguna)
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner="Memuat graf OpenSanctions (±85 ribu entitas)...")
def muat():
    data = muat_data.muat_semua()
    G = graf.bangun_graf(data.simpul, data.relasi)
    H = graf.tak_berarah(G)
    return data, G, H, graf.derajat(H)


data, G, H, DERAJAT = muat()
simpul, relasi, meta = data.simpul, data.relasi, data.meta
JUDUL_DATASET = muat_data.judul_dataset(data.dataset)


@st.cache_data(show_spinner=False)
def ringkasan_cache():
    return graf.ringkasan(H, simpul, relasi)


@st.cache_data(show_spinner=False)
def kapal_cache():
    return graf.tabel_kapal(G, simpul)


@st.cache_data(show_spinner=False)
def paparan_cache(n: int):
    return graf.paparan(H, simpul, n)


@st.cache_data(show_spinner=False)
def komponen_cache():
    return graf.ukuran_komponen(H)


def cari_id(nama: str, tipe: str | None = None) -> str | None:
    hasil = graf.cari(simpul, nama, DERAJAT, 5, tipe)
    cocok = hasil[hasil["nama"].str.lower() == nama.lower()]
    if not cocok.empty:
        return cocok.index[0]
    return hasil.index[0] if not hasil.empty else None


def label_hasil(id_: str) -> str:
    s = simpul.loc[id_]
    negara = ", ".join(nama_negara(k) for k in str(s["negara"]).split("; ")[:2] if k)
    tanda = "●" if s["tersanksi"] else "○"
    ekstra = f" · {negara}" if negara else ""
    return f"{tanda} {s['nama'][:48]} · {label_tipe(s['tipe'])}{ekstra} · {int(DERAJAT.get(id_, 0))} relasi"


def kotak_cari(label: str, kunci: str, bantuan: str = "", tipe: str | None = None) -> str | None:
    """Kotak teks + selectbox hasil; mengembalikan id entitas terpilih atau None."""
    teks = st.text_input(label, key=f"{kunci}_teks", placeholder="nama, alias, IMO, atau MMSI", help=bantuan)
    if len(teks.strip()) < 2:
        return None
    hasil = graf.cari(simpul, teks, DERAJAT, 25, tipe)
    if hasil.empty:
        st.caption("Tidak ada yang cocok. Coba ejaan Latin atau nama belakang saja.")
        return None
    return st.selectbox("Hasil", hasil.index.tolist(), format_func=label_hasil, key=f"{kunci}_pilih",
                        label_visibility="collapsed")


# ----------------------------------------------------------------------------
# 2. STATE EXPLORER
# ----------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("pusat", None)
ss.setdefault("tampil", [])
ss.setdefault("terpilih", None)
ss.setdefault("radius", 1)
ss.setdefault("maks_simpul", 80)


def mulai_dari(id_: str) -> None:
    """Jadikan satu entitas pusat explorer dan hitung ego-graf di sekelilingnya."""
    ss.pusat = id_
    ss.terpilih = id_
    ss.tampil = graf.ego(H, id_, ss.radius, ss.maks_simpul)


def perluas_simpul(id_: str) -> None:
    ss.tampil = graf.perluas(H, ss.tampil, id_, 40)
    ss.terpilih = id_


def sembunyikan(ids: list[str]) -> None:
    buang = set(ids) - {ss.pusat}
    ss.tampil = [i for i in ss.tampil if i not in buang]
    if ss.terpilih in buang:
        ss.terpilih = ss.pusat


def aksi_graf() -> None:
    """Callback komponen Cytoscape: klik simpul -> pilih; dua kali klik/expand -> perluas; delete -> sembunyikan."""
    nilai = ss.get("graf_utama") or {}
    aksi, isi = nilai.get("action"), nilai.get("data") or {}
    if aksi == "klik_simpul" and isi.get("target_group") == "nodes":
        ss.terpilih = isi.get("target_id")
    elif aksi == "expand":
        for i in isi.get("node_ids", []):
            perluas_simpul(i)
    elif aksi == "remove":
        sembunyikan(isi.get("node_ids", []))


# ----------------------------------------------------------------------------
# 3. SIDEBAR
# ----------------------------------------------------------------------------
with st.sidebar:
    st.title("🕸️ Gotham Lite")
    st.caption("Link analysis atas data sanksi publik: orang, perusahaan, kapal, dan siapa terhubung ke siapa.")

    st.subheader("🔍 Cari entitas")
    id_cari = kotak_cari("Nama, alias, IMO, atau MMSI", "cari_utama",
                         "● = ada di daftar sanksi, ○ = hanya terhubung. Minimal 2 huruf.")
    if id_cari and st.button("Tampilkan jaringannya", type="primary", use_container_width=True):
        mulai_dari(id_cari)

    st.subheader("🎯 Kasus siap pakai")
    for judul, nama, tipe, keterangan in KASUS:
        if st.button(judul, use_container_width=True, help=keterangan):
            id_kasus = cari_id(nama, tipe)
            if id_kasus:
                mulai_dari(id_kasus)
            else:
                st.warning(f"'{nama}' tidak ditemukan di snapshot ini.")

    st.subheader("⚙️ Pengaturan graf")
    radius_baru = st.radio("Kedalaman awal", [1, 2], index=ss.radius - 1, horizontal=True,
                           format_func=lambda r: f"{r} lompatan", help="Berapa lompatan dari pusat yang langsung ditampilkan.")
    maks_baru = st.slider("Maksimum simpul", 20, 250, ss.maks_simpul, 10,
                          help="Bila tetangga lebih banyak dari ini, yang tersanksi dan kapal/orang diprioritaskan.")
    if (radius_baru, maks_baru) != (ss.radius, ss.maks_simpul):
        ss.radius, ss.maks_simpul = radius_baru, maks_baru
        if ss.pusat:
            mulai_dari(ss.pusat)
    tata_letak = st.selectbox("Tata letak", list(TATA_LETAK), 0)
    tampil_label_sisi = st.toggle("Tulis jenis relasi di garis", value=False,
                                  help="Berguna untuk graf kecil; pada graf besar tulisan saling tumpang tindih.")

    st.divider()
    mode_belajar = st.toggle("🎓 Learning mode", value=False,
                             help="Tampilkan penjelasan konsep graf dan potongan kode di setiap tab.")
    st.caption(f"Snapshot OpenSanctions {meta.get('dibangun_pada', '')[:10]} · "
               f"{angka(meta['jumlah_simpul'])} simpul · {angka(meta['jumlah_relasi'])} relasi")


def belajar(judul: str, isi: str) -> None:
    if mode_belajar:
        with st.expander(f"🎓 Learning mode: {judul}", expanded=False):
            st.markdown(isi)


# ----------------------------------------------------------------------------
# 4. JUDUL + RINGKASAN ANGKA
# ----------------------------------------------------------------------------
st.title("🕸️ Gotham Lite")
st.markdown(
    "**Everyone is connected to someone.** Versi mini perangkat analisis keterkaitan ala intelijen: "
    f"**{angka(meta['jumlah_simpul'])} entitas** dan **{angka(meta['jumlah_relasi'])} relasi** dari OpenSanctions, "
    "dirangkai menjadi satu graf. Cari satu nama, klik simpulnya, perluas tetangganya, dan temukan jalur antara "
    "dua entitas yang tampak tidak berhubungan."
)
R = ringkasan_cache()
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Entitas", angka(R["simpul"]))
k2.metric("Relasi", angka(R["relasi"]))
k3.metric("Tersanksi", angka(R["tersanksi"]), help="Entitas bertopik sanction / sanction.linked / export.control.")
k4.metric("Kapal", angka(R["kapal"]))
k5.metric("Komponen terhubung", angka(R["komponen"]), help="Kelompok entitas yang saling terhubung, terpisah dari kelompok lain.")
k6.metric("Komponen terbesar", angka(R["komponen_terbesar"]), help="Jumlah entitas dalam gugus terbesar.")

tab_explorer, tab_jalur, tab_kapal, tab_stat, tab_data, tab_cara = st.tabs(
    ["🕸️ Explorer", "🔗 Connections", "🚢 Shadow fleet", "📊 Network stats", "📋 Data & Sources", "🧭 How it works"]
)

# ----------------------------------------------------------------------------
# 5. TAB EXPLORER
# ----------------------------------------------------------------------------
with tab_explorer:
    if not ss.pusat:
        st.info("Mulai dari sidebar: ketik nama (misalnya *Prigozhin*, *Rotenberg*, *Shamkhani*) atau pilih salah satu "
                "kasus siap pakai. Lalu klik simpul untuk melihat detailnya, klik dua kali untuk memperluas tetangganya.")
        st.markdown("**Legenda warna**")
        kol = st.columns(len(WARNA_TIPE) - 2)
        for kolom, (t, w) in zip(kol, [(t, w) for t, w in WARNA_TIPE.items() if t not in ("CryptoWallet", "Asset")]):
            kolom.markdown(f"<span style='color:{w};font-size:22px'>●</span> {label_tipe(t)}", unsafe_allow_html=True)
        st.caption("Warna terang = ada di daftar sanksi; warna redup = tidak tersanksi, hanya terhubung. ★ = pusat graf.")
    else:
        tersembunyi = graf.jumlah_tersembunyi(H, ss.tampil)
        elemen = graf.elemen_cytoscape(G, simpul, ss.tampil, tersembunyi, ss.pusat)
        for n in elemen["nodes"]:
            d = n["data"]
            if d["id"] == ss.pusat:
                d["nama"] = "★ " + d["nama"]
            elif d["tetangga_tersembunyi"]:
                d["nama"] = f"{d['nama']} (+{d['tetangga_tersembunyi']})"
        gaya_sisi = GAYA_RELASI if tampil_label_sisi else GAYA_RELASI_POLOS

        kiri, kanan = st.columns([2.1, 1])
        with kiri:
            pusat = simpul.loc[ss.pusat]
            st.markdown(f"#### Jaringan di sekitar **{pusat['nama']}** · {len(ss.tampil)} simpul · {len(elemen['edges'])} relasi")
            st.caption("Klik simpul = detail · klik dua kali atau tombol ⤢ = perluas tetangga · Delete = sembunyikan · "
                       "angka (+n) = tetangga yang belum ditampilkan.")
            st_link_analysis(
                elemen, layout=TATA_LETAK[tata_letak], node_styles=GAYA_SIMPUL, edge_styles=gaya_sisi, height=620,
                key="graf_utama", on_change=aksi_graf, node_actions=["remove", "expand"],
                events=[Event("klik_simpul", "tap", "node")],
            )
            # Legenda ringkas di bawah graf.
            leg = " &nbsp; ".join(
                f"<span style='color:{w}'>●</span> {label_tipe(t)}" for t, w in WARNA_TIPE.items() if t not in ("CryptoWallet", "Asset")
            )
            leg_sisi = " &nbsp; ".join(
                f"<span style='color:{WARNA_RELASI[t]}'>━</span> {label_relasi(t)}"
                for t in ("Ownership", "Directorship", "Membership", "Family", "Representation", "UnknownLink")
            )
            st.markdown(f"<div style='font-size:13px;color:#9ca3af'>{leg} &nbsp;·&nbsp; redup = tidak tersanksi<br>{leg_sisi}</div>",
                        unsafe_allow_html=True)

        with kanan:
            id_t = ss.terpilih if ss.terpilih in simpul.index else ss.pusat
            s = simpul.loc[id_t]
            warna = WARNA_TIPE.get(s["tipe"], "#9ca3af")
            status = ("<span style='background:#7f1d1d;color:#fecaca;padding:2px 8px;border-radius:10px;font-size:12px'>TERSANKSI</span>"
                      if s["tersanksi"] else
                      "<span style='background:#1f2937;color:#d1d5db;padding:2px 8px;border-radius:10px;font-size:12px'>TIDAK DALAM DAFTAR</span>")
            st.markdown(
                f"<div style='border-left:4px solid {warna};padding-left:10px'>"
                f"<div style='font-size:12px;color:{warna};text-transform:uppercase;letter-spacing:.08em'>{label_tipe(s['tipe'])}</div>"
                f"<div style='font-size:20px;font-weight:700;line-height:1.2'>{s['nama']}</div>"
                f"<div style='margin-top:6px'>{status}</div></div>", unsafe_allow_html=True)

            baris = []
            if s["alias"]:
                baris.append(("Alias", s["alias"]))
            negara = ", ".join(nama_negara(k) for k in str(s["negara"]).split("; ") if k)
            if negara:
                baris.append(("Negara", negara))
            if s["tipe"] == "Person" and s["tanggal"]:
                baris.append(("Lahir", s["tanggal"]))
            elif s["tipe"] in ("Company", "Organization", "LegalEntity") and s["tanggal"]:
                baris.append(("Berdiri", s["tanggal"]))
            if s["jabatan"]:
                baris.append(("Jabatan", s["jabatan"][:160] + ("…" if len(s["jabatan"]) > 160 else "")))
            if s["tipe"] == "Vessel":
                baris += [("Bendera", nama_negara(s["bendera"]) or "-"), ("IMO", s["imo"] or "-"),
                          ("MMSI", s["mmsi"] or "-"), ("Jenis", s["jenis_kapal"] or "-"),
                          ("Dibangun", s["tanggal"][:4] if s["tanggal"] else "-")]
            if s["program"]:
                baris.append(("Program sanksi", s["program"]))
            daftar_ds = [JUDUL_DATASET.get(d_, d_) for d_ in str(s["dataset"]).split("; ") if d_][:5]
            if daftar_ds:
                baris.append(("Sumber", "; ".join(daftar_ds)))
            if s["terakhir_berubah"]:
                baris.append(("Diperbarui", s["terakhir_berubah"]))
            st.markdown("\n".join(f"- **{k}:** {v}" for k, v in baris))
            if s["catatan"]:
                st.caption(s["catatan"])
            st.markdown(f"[Profil lengkap di OpenSanctions ↗]({muat_data.url_opensanctions(id_t)})")

            b1, b2, b3 = st.columns(3)
            sisa = tersembunyi.get(id_t, 0)
            if b1.button("★ Jadikan pusat", use_container_width=True, disabled=id_t == ss.pusat):
                mulai_dari(id_t)
                st.rerun()
            if b2.button(f"⤢ Perluas (+{sisa})", use_container_width=True, disabled=sisa == 0):
                perluas_simpul(id_t)
                st.rerun()
            if b3.button("✕ Sembunyikan", use_container_width=True, disabled=id_t == ss.pusat):
                sembunyikan([id_t])
                st.rerun()

            tetangga = graf.tetangga(G, id_t)
            st.markdown(f"**Relasi ({len(tetangga)})**")
            if tetangga:
                df_t = pd.DataFrame(tetangga)
                df_t["Relasi"] = [
                    (f"{label_relasi(r)} →" if a == "keluar" else f"← {label_relasi(r)}") for r, a in zip(df_t["relasi"], df_t["arah"])
                ]
                df_t["Entitas"] = ["● " + n if t else "○ " + n for n, t in zip(df_t["nama"], df_t["tersanksi"])]
                df_t["Tipe"] = df_t["tipe"].map(label_tipe)
                df_t["Peran"] = df_t["peran"].str.slice(0, 60)
                st.dataframe(df_t[["Relasi", "Entitas", "Tipe", "Peran"]], hide_index=True, use_container_width=True, height=300)
                st.caption("→ dibaca dari entitas ini ke tetangga (misalnya *memiliki →* = entitas ini pemiliknya); "
                           "← sebaliknya.")

    belajar("ego-graf dan BFS", """
Yang kamu lihat di tab ini adalah **ego-graf**: satu simpul pusat ditambah semua simpul yang bisa dicapai dalam *k*
lompatan. Cara menghitungnya adalah **penelusuran melebar (breadth-first search, BFS)**: mulai dari pusat, ambil semua
tetangganya (lapis 1), lalu semua tetangga dari lapis 1 yang belum pernah dilihat (lapis 2), dan seterusnya.

```python
def ego(H, pusat, radius=1, maks_simpul=120):
    terpilih, terlihat, lapis = [pusat], {pusat}, [pusat]
    for _ in range(radius):
        kandidat = {v for n in lapis for v in H.neighbors(n) if v not in terlihat}
        lapis = sorted(kandidat, key=prioritas)[:maks_simpul - len(terpilih)]
        terpilih.extend(lapis); terlihat.update(lapis)
    return terpilih
```

Masalah klasik analisis keterkaitan adalah **simpul hub**: satu kementerian bisa punya ribuan anak perusahaan. Kalau semua
ditampilkan, graf menjadi "bola rambut" yang tidak terbaca. Karena itu ada batas `maks_simpul` dan urutan prioritas:
entitas tersanksi dahulu, lalu kapal dan orang, lalu yang paling banyak relasinya. Tetangga yang tidak ikut ditampilkan
dihitung dan ditulis sebagai `(+n)`, dan bisa dibuka dengan tombol perluas.

Grafnya digambar oleh **Cytoscape.js** lewat komponen `st-link-analysis`. Setiap klik di kanvas dikirim kembali ke Python
sebagai `{"action": "klik_simpul", "data": {"target_id": ...}}`, lalu `st.session_state` diperbarui dan halaman dirender ulang.
Itulah pola umum komponen interaktif Streamlit: JavaScript menggambar, Python memegang keadaan.
""")

# ----------------------------------------------------------------------------
# 6. TAB CONNECTIONS (jalur antara dua entitas)
# ----------------------------------------------------------------------------
with tab_jalur:
    st.markdown("#### Apakah A terhubung ke B? Lewat siapa?")
    st.caption("Mencari sampai tiga jalur terpendek di graf tak berarah, lalu membacakannya sebagai kalimat.")
    PASANGAN = [("Vladimir Putin", "Igor Sechin"), ("Yevgeny Prigozhin", "Kim Jong-un"),
                ("Sa'id Ahmad Muhammad Al-Jamal", "Ali Khamenei"), ("Sa'id Ahmad Muhammad Al-Jamal", "Vladimir Putin")]
    pilih = st.radio("Contoh pasangan", ["Pilih sendiri"] + [f"{a} ↔ {b}" for a, b in PASANGAN], horizontal=True,
                     label_visibility="collapsed")
    ca, cb = st.columns(2)
    if pilih == "Pilih sendiri":
        with ca:
            id_a = kotak_cari("Entitas A", "jalur_a")
        with cb:
            id_b = kotak_cari("Entitas B", "jalur_b")
    else:
        nama_a, nama_b = PASANGAN[[f"{a} ↔ {b}" for a, b in PASANGAN].index(pilih)]
        id_a, id_b = cari_id(nama_a), cari_id(nama_b)
        ca.info(f"A: {simpul.loc[id_a, 'nama'] if id_a else nama_a}")
        cb.info(f"B: {simpul.loc[id_b, 'nama'] if id_b else nama_b}")

    maks_panjang = st.slider("Panjang jalur maksimum (relasi)", 2, 8, 6, help="Jalur yang lebih panjang dari ini tidak dicari; "
                             "makin panjang, makin lemah maknanya.")
    if id_a and id_b:
        if id_a == id_b:
            st.warning("Pilih dua entitas yang berbeda.")
        else:
            jalur = graf.jalur_terpendek(H, id_a, id_b, maks_jalur=3, maks_panjang=maks_panjang)
            if not jalur:
                st.error(f"Tidak ada jalur (sampai {maks_panjang} relasi) antara keduanya di snapshot ini. "
                         "Keduanya mungkin berada di komponen terhubung yang berbeda, atau jalurnya lebih panjang.")
            else:
                st.success(f"Ditemukan {len(jalur)} jalur; yang terpendek {len(jalur[0]) - 1} relasi.")
                gabung: list[str] = []
                for j in jalur:
                    for n in j:
                        if n not in gabung:
                            gabung.append(n)
                kj, kk = st.columns([1.6, 1])
                with kj:
                    el = graf.elemen_cytoscape(G, simpul, gabung, pusat=id_a)
                    for n in el["nodes"]:
                        if n["data"]["id"] in (id_a, id_b):
                            n["data"]["nama"] = ("A: " if n["data"]["id"] == id_a else "B: ") + n["data"]["nama"]
                    st_link_analysis(el, layout="dagre", node_styles=GAYA_SIMPUL, edge_styles=GAYA_RELASI,
                                     height=520, key="graf_jalur")
                with kk:
                    for i, j in enumerate(jalur, 1):
                        st.markdown(f"**Jalur {i}** · {len(j) - 1} relasi")
                        for kalimat in graf.ceritakan_jalur(G, j):
                            st.markdown(f"- {kalimat}")
                    if st.button("Buka jalur ini di Explorer", key="buka_jalur"):
                        ss.pusat, ss.terpilih, ss.tampil = id_a, id_a, gabung
                        st.toast("Jalur dimuat ke tab Explorer.")
    belajar("jalur terpendek", """
Pertanyaan "lewat siapa A terhubung ke B" adalah soal **jalur terpendek** di graf tak berbobot. networkx menyelesaikannya
dengan BFS dua arah (`nx.shortest_path`), dan untuk beberapa jalur alternatif ada `nx.shortest_simple_paths` (algoritma
Yen) yang menghasilkan jalur dari yang terpendek ke yang lebih panjang satu per satu.

```python
for jalur in nx.shortest_simple_paths(H, a, b):
    if len(jalur) - 1 > 6:
        break           # terlalu panjang untuk dibaca; berhenti
    hasil.append(jalur)
    if len(hasil) == 3:
        break
```

Dua catatan penting. Pertama, jalur dicari di graf **tak berarah**: "A memiliki B" dan "B dimiliki A" sama saja untuk
pertanyaan keterhubungan. Kedua, jalur pendek **bukan bukti**: dua orang bisa "terhubung" hanya karena sama-sama anggota
satu partai. Karena itu setiap langkah dibacakan lengkap dengan jenis relasinya, supaya pembaca bisa menilai sendiri.
""")

# ----------------------------------------------------------------------------
# 7. TAB SHADOW FLEET (kapal)
# ----------------------------------------------------------------------------
with tab_kapal:
    kapal = kapal_cache()
    kapal_s = kapal[kapal["tersanksi"] == 1]
    foc = kapal_s["bendera"].isin(muat_data.BENDERA_KEMUDAHAN).mean() if len(kapal_s) else 0
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Kapal tersanksi", angka(len(kapal_s)))
    m2.metric("Punya MMSI", angka((kapal_s["mmsi"] != "").sum()), help="Bisa dicocokkan dengan siaran AIS.")
    tanker = kapal_s["jenis_kapal"].str.contains("Tanker", case=False).mean() if len(kapal_s) else 0
    m3.metric("Tanker", f"{tanker:.0%}", help="Porsi kapal tersanksi yang berjenis tanker minyak/kimia/gas.")
    m4.metric("Bendera kemudahan", f"{foc:.0%}", help="Terdaftar di negara 'flag of convenience' menurut daftar ITF (Panama, Liberia, Kamerun, Gabon, ...).")
    umur = (2026 - kapal_s["tahun"].dropna().astype(int))
    m5.metric("Umur median", f"{int(umur.median())} tahun" if len(umur) else "-", help="Armada bayangan identik dengan tanker tua.")

    g1, g2 = st.columns(2)
    with g1:
        bendera = kapal_s["nama_bendera"].replace("", "Tidak tercatat").value_counts().head(15).reset_index()
        bendera.columns = ["bendera", "jumlah"]
        fig = px.bar(bendera.sort_values("jumlah"), x="jumlah", y="bendera", orientation="h",
                     title="Bendera kapal tersanksi (15 teratas)", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{y}: %{x} kapal<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 440), use_container_width=True)
    with g2:
        jenis = kapal_s["jenis_kapal"].replace("", "Tidak tercatat").value_counts().head(12).reset_index()
        jenis.columns = ["jenis", "jumlah"]
        fig = px.bar(jenis.sort_values("jumlah"), x="jumlah", y="jenis", orientation="h",
                     title="Jenis kapal", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{y}: %{x} kapal<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 440), use_container_width=True)

    g3, g4 = st.columns(2)
    with g3:
        otoritas = graf.hitung_dataset(kapal_s, JUDUL_DATASET, 10)
        otoritas["judul"] = otoritas["judul"].str.slice(0, 48)
        fig = px.bar(otoritas.sort_values("jumlah"), x="jumlah", y="judul", orientation="h",
                     title="Siapa yang mendaftarkan (dataset sumber)", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{y}: %{x} kapal<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 400), use_container_width=True)
    with g4:
        th = kapal_s["tahun"].dropna().astype(int)
        th = th[(th > 1950) & (th <= 2026)]
        fig = px.histogram(th, nbins=30, title="Tahun pembuatan kapal tersanksi", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{x}: %{y} kapal<extra></extra>", marker_line_width=0)
        fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="kapal", bargap=0.08)
        st.plotly_chart(rapikan(fig, 400), use_container_width=True)

    st.markdown("#### Daftar kapal")
    f1, f2, f3 = st.columns([1, 1, 2])
    pil_bendera = f1.multiselect("Bendera", sorted(kapal_s["nama_bendera"].replace("", "Tidak tercatat").unique()))
    pil_jenis = f2.multiselect("Jenis", sorted(kapal_s["jenis_kapal"].replace("", "Tidak tercatat").unique()))
    teks_kapal = f3.text_input("Cari nama / IMO / MMSI / pemilik", key="cari_kapal")
    tampil_kapal = kapal_s.copy()
    tampil_kapal["nama_bendera"] = tampil_kapal["nama_bendera"].replace("", "Tidak tercatat")
    tampil_kapal["jenis_kapal"] = tampil_kapal["jenis_kapal"].replace("", "Tidak tercatat")
    if pil_bendera:
        tampil_kapal = tampil_kapal[tampil_kapal["nama_bendera"].isin(pil_bendera)]
    if pil_jenis:
        tampil_kapal = tampil_kapal[tampil_kapal["jenis_kapal"].isin(pil_jenis)]
    if teks_kapal.strip():
        q = teks_kapal.strip().lower()
        tampil_kapal = tampil_kapal[
            tampil_kapal["nama"].str.lower().str.contains(q, regex=False) | tampil_kapal["imo"].str.contains(q, regex=False)
            | tampil_kapal["mmsi"].str.contains(q, regex=False) | tampil_kapal["pemilik"].str.lower().str.contains(q, regex=False)
        ]
    st.dataframe(
        tampil_kapal.sort_values("jumlah_relasi", ascending=False)[
            ["nama", "nama_bendera", "jenis_kapal", "imo", "mmsi", "tahun", "program", "pemilik", "jumlah_relasi"]
        ].rename(columns={"nama": "Kapal", "nama_bendera": "Bendera", "jenis_kapal": "Jenis", "imo": "IMO", "mmsi": "MMSI",
                          "tahun": "Dibangun", "program": "Program", "pemilik": "Pemilik / operator tercatat",
                          "jumlah_relasi": "Relasi"}),
        hide_index=True, use_container_width=True, height=380,
    )
    st.caption(f"{angka(len(tampil_kapal))} kapal ditampilkan. Klik judul kolom untuk mengurutkan.")

    st.markdown("#### Rantai kepemilikan sebuah kapal")
    pilihan_kapal = kapal_s[kapal_s["jumlah_relasi"] > 0].sort_values("jumlah_relasi", ascending=False)
    id_kapal = st.selectbox("Pilih kapal (diurutkan dari yang paling banyak relasinya)", pilihan_kapal.index.tolist(),
                            format_func=lambda i: f"{simpul.loc[i, 'nama']} · {nama_negara(simpul.loc[i, 'bendera']) or '?'} · "
                                                  f"IMO {simpul.loc[i, 'imo'] or '-'} · {int(DERAJAT.get(i, 0))} relasi")
    if id_kapal:
        rantai = graf.rantai_pemilik(G, id_kapal, maks_hop=4)
        rk1, rk2 = st.columns([1.4, 1])
        with rk1:
            ids_rantai = [id_kapal] + [n for r in rantai for n, _ in r]
            ids_rantai = list(dict.fromkeys(ids_rantai))[:60]
            st_link_analysis(graf.elemen_cytoscape(G, simpul, ids_rantai, pusat=id_kapal), layout="breadthfirst",
                             node_styles=GAYA_SIMPUL, edge_styles=GAYA_RELASI, height=420, key="graf_kapal")
        with rk2:
            if not rantai:
                st.info("Tidak ada relasi 'masuk' (pemilik/operator) yang tercatat untuk kapal ini.")
            for r in rantai[:8]:
                teks = " ← ".join(f"**{simpul.loc[n, 'nama'][:40]}** ({label_relasi(t)})" for n, t in r)
                st.markdown(f"- {simpul.loc[id_kapal, 'nama']} ← {teks}")
            if len(rantai) > 8:
                st.caption(f"... dan {len(rantai) - 8} rantai lain.")
            if st.button("Buka kapal ini di Explorer", key="buka_kapal"):
                mulai_dari(id_kapal)
                st.toast("Dimuat ke tab Explorer.")

    st.markdown("#### 📡 Live AIS: kapal tersanksi mana yang sedang memancar?")
    kunci_ais = ais.ambil_api_key()
    kapal_mmsi = kapal_s[kapal_s["mmsi"].str.fullmatch(r"\d{9}")]
    KELOMPOK_AIS = {
        "Paling banyak relasi di graf": kapal_mmsi.sort_values("jumlah_relasi", ascending=False),
        "Bendera Rusia": kapal_mmsi[kapal_mmsi["bendera"] == "ru"],
        "Bendera Iran": kapal_mmsi[kapal_mmsi["bendera"] == "ir"],
        "Bendera Korea Utara": kapal_mmsi[kapal_mmsi["bendera"] == "kp"],
        "Bendera kemudahan (Panama, Gabon, Kamerun, ...)": kapal_mmsi[kapal_mmsi["bendera"].isin(muat_data.BENDERA_KEMUDAHAN)],
        "Tanker": kapal_mmsi[kapal_mmsi["jenis_kapal"].str.contains("Tanker", case=False)],
        "Terbaru masuk daftar": kapal_mmsi.sort_values("pertama_terlihat", ascending=False),
    }
    with st.expander("Dengarkan siaran AIS (perlu kunci aisstream.io gratis)", expanded=bool(kunci_ais)):
        st.markdown(
            "AIS adalah sinyal identitas dan posisi yang wajib dipancarkan kapal besar. Dengan kunci gratis dari "
            "[aisstream.io](https://aisstream.io), aplikasi meminta server mengirim hanya pesan dari MMSI kapal tersanksi "
            f"(batas server **{ais.MAKS_MMSI} MMSI per sesi**, dari {angka(len(kapal_mmsi))} kapal tersanksi yang punya MMSI), "
            "lalu mendengarkan beberapa puluh detik. Kapal yang mematikan AIS (praktik umum armada bayangan) tidak akan "
            "terdengar, dan itu sendiri sebuah temuan."
        )
        if not kunci_ais:
            kunci_manual = st.text_input("Kunci API aisstream.io", type="password",
                                         help="Di Streamlit Cloud, isi Secrets: [aisstream]\napi_key = \"...\"")
            if kunci_manual.strip():
                os.environ["AISSTREAM_API_KEY"] = kunci_manual.strip()
                kunci_ais = kunci_manual.strip()
        ka1, ka2 = st.columns([2, 1])
        nama_kelompok = ka1.selectbox("Kelompok kapal yang dipantau", list(KELOMPOK_AIS))
        durasi = ka2.slider("Lama mendengarkan (detik)", 15, 90, 30, 5)
        kelompok = KELOMPOK_AIS[nama_kelompok]
        daftar_mmsi = ais.pilih_mmsi(kelompok["mmsi"].tolist())
        st.caption(f"{len(daftar_mmsi)} MMSI dikirim ke server" +
                   (f" (dari {angka(len(kelompok))} kapal di kelompok ini; sisanya di luar batas sesi)." if len(kelompok) > len(daftar_mmsi) else "."))
        if st.button("📡 Dengarkan sekarang", type="primary", disabled=not kunci_ais or not daftar_mmsi):
            with st.spinner(f"Mendengarkan aisstream.io selama {durasi} detik..."):
                try:
                    df_pos, n_pesan, n_kapal = ais.dengarkan(kunci_ais, daftar_mmsi, durasi)
                    ss["ais_hasil"] = (ais.gabung_dengan_kapal(df_pos, kapal_s), n_pesan, n_kapal, ais.sekarang_utc(),
                                       nama_kelompok, len(daftar_mmsi))
                except ais.AisError as exc:
                    st.error(str(exc))
        if "ais_hasil" in ss:
            df_pos, n_pesan, n_kapal, waktu, kel_hasil, n_dipantau = ss["ais_hasil"]
            a1, a2, a3 = st.columns(3)
            a1.metric("MMSI dipantau", angka(n_dipantau), help=kel_hasil)
            a2.metric("Pesan diterima", angka(n_pesan))
            a3.metric("Kapal tersanksi terdengar", angka(len(df_pos)))
            if df_pos.empty:
                st.info("Tidak ada kapal dalam kelompok ini yang memancar selama rentang tadi. Coba kelompok lain atau "
                        "durasi lebih lama; cakupan penerima aisstream terbaik di pesisir Eropa dan Asia Timur, dan banyak "
                        "kapal tersanksi memang mematikan AIS.")
            else:
                fig = go.Figure(go.Scattergeo(
                    lat=df_pos["lat"], lon=df_pos["lon"], mode="markers",
                    marker=dict(size=10, color=MERAH, line=dict(width=1, color="#ffffff")),
                    text=[f"{n or a}<br>Bendera: {nama_negara(b)}<br>IMO {i} · MMSI {m}<br>{s}<br>{sog} knot"
                          for n, a, b, i, m, s, sog in zip(df_pos["nama"].fillna(""), df_pos["nama_ais"], df_pos["bendera"].fillna(""),
                                                           df_pos["imo"].fillna(""), df_pos["mmsi"], df_pos["status_nav"],
                                                           df_pos["sog_knot"].fillna(0).round(1))],
                    hovertemplate="%{text}<extra></extra>",
                ))
                fig.update_geos(projection_type="natural earth", showcountries=True, countrycolor="#243044",
                                showland=True, landcolor="#151a24", showocean=True, oceancolor="#0b0e14",
                                coastlinecolor="#2b3a55", bgcolor="rgba(0,0,0,0)")
                fig.update_layout(title=f"Kapal tersanksi yang memancar AIS · {kel_hasil} · {waktu:%d %b %Y %H:%M} UTC")
                st.plotly_chart(rapikan(fig, 480), use_container_width=True)
                st.dataframe(df_pos[["nama", "nama_ais", "bendera", "imo", "mmsi", "lat", "lon", "sog_knot", "status_nav", "program"]]
                             .rename(columns={"nama": "Nama di daftar", "nama_ais": "Nama di AIS", "bendera": "Bendera",
                                              "sog_knot": "Kecepatan (knot)", "status_nav": "Status", "program": "Program"}),
                             hide_index=True, use_container_width=True)
    belajar("armada bayangan dan AIS", """
"**Armada bayangan**" (shadow fleet) adalah sebutan untuk ratusan tanker tua yang mengangkut minyak Rusia, Iran, dan
Venezuela sambil menghindari sanksi: berbendera kemudahan (Panama, Gabon, Kamerun), berpindah pemilik lewat perusahaan
cangkang, asuransi tidak jelas, dan sering mematikan AIS. Tiga pola itu semuanya bisa dilihat di data:

- **Bendera**: bandingkan grafik bendera dengan daftar *flag of convenience* ITF (`BENDERA_KEMUDAHAN` di `src/muat_data.py`).
- **Umur**: tanker komersial normal dipensiunkan sekitar 20 tahun; lihat median umur di atas.
- **Pemilik berlapis**: `rantai_pemilik()` menelusuri relasi masuk (Ownership, Directorship, Representation, UnknownLink)
  sampai empat lapis, dengan DFS sederhana yang menyimpan jejak.

```python
def telusur(n, jejak, terlihat):
    atas = [(u, d["tipe"]) for u, _, d in G.in_edges(n, data=True) if d["tipe"] in DIIKUTI and u not in terlihat]
    if not atas or len(jejak) >= maks_hop:
        rantai.append(jejak); return
    for u, t in atas:
        telusur(u, jejak + [(u, t)], terlihat | {u})
```

Untuk AIS: setiap kapal punya **MMSI** (identitas radio 9 digit) dan **IMO** (nomor lambung seumur hidup). Daftar sanksi
mencatat keduanya, sehingga pesan AIS bisa dicocokkan langsung lewat MMSI. aisstream menerima paling banyak 200 MMSI per
langganan, karena itu kapal dipilih per kelompok. Percobaan pertama berlangganan seluruh dunia tanpa filter dan menyaring
di sisi klien; server memutus koneksi karena klien tidak sanggup mengikuti ribuan pesan per detik. Kode WebSocket-nya ada
di `src/ais.py`.
""")

# ----------------------------------------------------------------------------
# 8. TAB NETWORK STATS
# ----------------------------------------------------------------------------
with tab_stat:
    s1, s2 = st.columns(2)
    with s1:
        tipe_df = simpul.groupby(["tipe", "tersanksi"]).size().reset_index(name="jumlah")
        tipe_df["Tipe"] = tipe_df["tipe"].map(label_tipe)
        tipe_df["Status"] = tipe_df["tersanksi"].map({1: "Tersanksi", 0: "Hanya terhubung"})
        fig = px.bar(tipe_df, x="jumlah", y="Tipe", color="Status", orientation="h", barmode="stack",
                     title="Entitas per tipe dan status", color_discrete_map={"Tersanksi": EMAS, "Hanya terhubung": ABU},
                     category_orders={"Tipe": [label_tipe(t) for t in ["Company", "Person", "Vessel", "Organization", "Airplane", "LegalEntity", "PublicBody", "Asset"]]})
        fig.update_traces(hovertemplate="%{y} · %{x}<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 380), use_container_width=True)
    with s2:
        rel_df = relasi["tipe"].value_counts().reset_index()
        rel_df.columns = ["tipe", "jumlah"]
        rel_df["Relasi"] = rel_df["tipe"].map(lambda t: f"{t} ({label_relasi(t)})")
        fig = px.bar(rel_df.sort_values("jumlah"), x="jumlah", y="Relasi", orientation="h", title="Jenis relasi",
                     color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{y}: %{x}<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 380), use_container_width=True)

    s3, s4 = st.columns(2)
    with s3:
        dist = graf.distribusi_derajat(H)
        fig = px.bar(dist, x="derajat", y="jumlah", title="Distribusi derajat (jumlah relasi per entitas)",
                     color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{x} relasi: %{y} entitas<extra></extra>", marker_line_width=0)
        fig.update_layout(xaxis_title="relasi per entitas", yaxis_title=None)
        st.plotly_chart(rapikan(fig, 360), use_container_width=True)
        st.caption(f"Median {R['derajat_median']:.0f} relasi, rata-rata {R['derajat_rata']:.1f}, maksimum {angka(R['derajat_maks'])}. "
                   "Sebagian kecil simpul memegang sebagian besar relasi, pola 'ekor panjang' yang khas jaringan sosial.")
    with s4:
        komp = komponen_cache()
        kd = pd.DataFrame({"peringkat": [f"#{i + 1}" for i in range(min(12, len(komp)))], "ukuran": komp[:12]})
        fig = px.bar(kd, x="peringkat", y="ukuran", title="12 komponen terhubung terbesar", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{x}: %{y} entitas<extra></extra>", marker_line_width=0)
        fig.update_layout(xaxis_title=None, yaxis_title="entitas", yaxis_type="log")
        st.plotly_chart(rapikan(fig, 360), use_container_width=True)
        st.caption(f"Komponen terbesar memuat {komp[0] / R['simpul']:.0%} entitas; {angka(len(komp))} komponen lain terpisah "
                   "(skala logaritmik).")

    st.markdown("#### Simpul paling terhubung")
    h1, h2, h3 = st.columns(3)
    for kolom, tipe, judul in ((h1, "Person", "Orang"), (h2, "Company", "Perusahaan"), (h3, "Vessel", "Kapal")):
        with kolom:
            hub = graf.peringkat_hub(H, simpul, tipe, 10)
            hub["Negara"] = hub["negara"].map(lambda t: ", ".join(nama_negara(k) for k in str(t).split("; ")[:2] if k))
            hub["Nama"] = ["● " + n if t else "○ " + n for n, t in zip(hub["nama"], hub["tersanksi"])]
            st.markdown(f"**{judul}**")
            st.dataframe(hub[["Nama", "Negara", "derajat"]].rename(columns={"derajat": "Relasi"}), hide_index=True,
                         use_container_width=True, height=390)

    st.markdown("#### Tidak dalam daftar, tetapi dekat")
    st.caption("Entitas yang tidak tersanksi, diurutkan dari yang paling banyak bertetangga langsung dengan entitas tersanksi. "
               "Pola khas analisis keterkaitan; sering berisi pihak netral (badan klasifikasi kapal, partai, bank) yang "
               "kebetulan menyentuh banyak nama.")
    pap = paparan_cache(20)
    if not pap.empty:
        pap["Tipe"] = pap["tipe"].map(label_tipe)
        pap["Negara"] = pap["negara"].map(lambda t: ", ".join(nama_negara(k) for k in str(t).split("; ")[:2] if k))
        st.dataframe(pap[["nama", "Tipe", "Negara", "tetangga_tersanksi", "derajat"]]
                     .rename(columns={"nama": "Entitas", "tetangga_tersanksi": "Tetangga tersanksi", "derajat": "Total relasi"}),
                     hide_index=True, use_container_width=True, height=380)

    s5, s6 = st.columns(2)
    with s5:
        neg = graf.hitung_per_negara(simpul[simpul["tersanksi"] == 1], 15)
        fig = px.bar(neg.sort_values("jumlah"), x="jumlah", y="negara", orientation="h",
                     title="Negara entitas tersanksi (15 teratas)", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{y}: %{x}<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 440), use_container_width=True)
    with s6:
        prog = graf.hitung_program(simpul, 15)
        fig = px.bar(prog.sort_values("jumlah"), x="jumlah", y="program", orientation="h",
                     title="Program sanksi terbanyak", color_discrete_sequence=[BIRU])
        fig.update_traces(hovertemplate="%{y}: %{x}<extra></extra>", marker_line_width=0)
        st.plotly_chart(rapikan(fig, 440), use_container_width=True)
    belajar("ukuran-ukuran jaringan", """
Beberapa istilah yang dipakai di tab ini:

- **Derajat** (degree): jumlah relasi sebuah simpul. Simpul berderajat tinggi disebut **hub**.
- **Komponen terhubung**: kelompok simpul yang saling bisa dicapai. Graf sanksi ternyata sangat terfragmentasi: ada
  ribuan komponen kecil (satu orang dan dua perusahaannya) dan satu komponen raksasa yang menyatukan Rusia, Iran, dan
  Korea Utara lewat perusahaan perantara.
- **Paparan** (exposure): untuk simpul yang tidak tersanksi, berapa tetangganya yang tersanksi. Ini versi paling
  sederhana dari "risiko menular" yang dipakai perangkat kepatuhan; versi lanjutannya memakai PageRank berpersonalisasi.

```python
deg = pd.Series(dict(H.degree()))
komponen = sorted((len(c) for c in nx.connected_components(H)), reverse=True)
paparan = {v: sum(H.nodes[u]["tersanksi"] for u in H.neighbors(v)) for v in H if not H.nodes[v]["tersanksi"]}
```

Grafik komponen memakai **skala logaritmik** karena komponen #1 ribuan kali lebih besar dari #12; pada skala biasa
sebelas batang lainnya tidak akan terlihat.
""")

# ----------------------------------------------------------------------------
# 9. TAB DATA & SOURCES
# ----------------------------------------------------------------------------
with tab_data:
    st.markdown(f"""
#### Sumber
- **[OpenSanctions](https://www.opensanctions.org)**, koleksi *default*: gabungan {angka(meta.get('jumlah_dataset', 0))}+ dataset
  resmi (OFAC AS, Uni Eropa, OFSI Inggris, DK PBB, NSDC Ukraina, SECO Swiss, dan lain-lain) ditambah pengayaan dari
  register perusahaan publik (EGRUL Rusia, Companies House, GLEIF, ICIJ Offshore Leaks) dan Wikidata. Data dalam format
  **FollowTheMoney (FtM)**, lisensi **CC BY-NC 4.0** (bebas untuk penggunaan non-komersial dengan atribusi).
- **[aisstream.io](https://aisstream.io)** (opsional): siaran AIS langsung untuk mencocokkan MMSI kapal tersanksi.

#### Cara data dipangkas
Koleksi *default* berisi ±3,9 juta entitas (2,5 GB). `scripts/bangun_data.py` menyimpan hanya yang relevan untuk
analisis keterkaitan:

1. **Benih** = entitas bertopik `sanction`, `sanction.linked`, `sanction.counter`, atau `export.control`
   ({angka(meta.get('benih_tersanksi', 0))} entitas).
2. **Relasi** disimpan bila menyentuh minimal satu benih. Relasi dari register perusahaan (`ext_*`) hanya disimpan bila
   salah satu ujungnya **orang atau kapal** tersanksi, karena lembaga negara yang disanksi tercatat memiliki ribuan badan
   usaha yang tidak menambah cerita. Setiap benih menyimpan paling banyak 60 tetangga yang tidak tersanksi.
3. **Simpul** = benih yang punya relasi + semua tetangganya. Entitas tersanksi yang tidak punya relasi tercatat
   (mayoritas daftar) tidak dimuat.

Hasil: **{angka(meta['jumlah_simpul'])} simpul** dan **{angka(meta['jumlah_relasi'])} relasi**, dibangun {meta.get('dibangun_pada', '')}.
GitHub Actions membangun ulang snapshot ini setiap awal bulan.

#### Keterbatasan
- Nama di graf **bukan bukti pelanggaran**. Entitas yang tidak tersanksi tampil karena punya relasi tercatat.
- OpenSanctions menggabungkan banyak sumber dengan kualitas berbeda; duplikat dan nama transliterasi ganda masih ada.
- Relasi `UnknownLink` berarti sumber menyebut keterkaitan tanpa merinci jenisnya.
- Pemangkasan 60 tetangga per benih membuat hub besar (kementerian, konglomerat) tampak lebih kecil dari aslinya.
- Jalur terpendek dicari di graf tak berarah, sehingga "A memiliki B" dan "B memiliki A" diperlakukan sama.
""")
    st.markdown("#### Dataset sumber yang muncul di graf")
    ds = data.dataset.head(40).copy()
    ds["judul"] = ds.apply(lambda r: f"[{r['judul']}]({r['url']})" if r["url"] else r["judul"], axis=1)
    ds["negara_penerbit"] = ds["negara_penerbit"].map(nama_negara)
    st.dataframe(ds[["judul", "penerbit", "negara_penerbit", "jumlah_simpul", "jumlah_relasi"]]
                 .rename(columns={"judul": "Dataset", "penerbit": "Penerbit", "negara_penerbit": "Negara",
                                  "jumlah_simpul": "Entitas", "jumlah_relasi": "Relasi"}),
                 hide_index=True, use_container_width=True, height=420,
                 column_config={"Dataset": st.column_config.LinkColumn("Dataset", display_text=r"\[(.*)\]")})
    d1, d2, d3 = st.columns(3)
    with open(os.path.join(muat_data.DIR_DATA, "simpul.csv.gz"), "rb") as f:
        d1.download_button("⬇️ simpul.csv.gz", f.read(), "simpul.csv.gz", "application/gzip", use_container_width=True)
    with open(os.path.join(muat_data.DIR_DATA, "relasi.csv.gz"), "rb") as f:
        d2.download_button("⬇️ relasi.csv.gz", f.read(), "relasi.csv.gz", "application/gzip", use_container_width=True)
    d3.download_button("⬇️ kapal_tersanksi.csv", kapal_cache().to_csv(index=False).encode(), "kapal_tersanksi.csv", "text/csv",
                       use_container_width=True)
    st.info(DISCLAIMER)

# ----------------------------------------------------------------------------
# 10. TAB HOW IT WORKS
# ----------------------------------------------------------------------------
with tab_cara:
    st.markdown("#### Alur data")
    st.graphviz_chart("""
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#151a24", color="#2b3a55", fontcolor="#e6edf3", fontname="Helvetica", fontsize=11];
  edge [color="#5b6b82", fontcolor="#9ca3af", fontname="Helvetica", fontsize=10];
  A [label="OpenSanctions\\nentities.ftm.json\\n3,9 juta entitas · 2,5 GB"];
  B [label="scripts/bangun_data.py\\nlintasan 1: benih + relasi\\nlintasan 2: simpul"];
  C [label="data/\\nsimpul.csv.gz · relasi.csv.gz\\ndataset.csv · META.json", fillcolor="#1f2937"];
  D [label="src/muat_data.py\\npandas + kamus label"];
  E [label="src/graf.py\\nnetworkx: ego, perluas,\\njalur, rantai, statistik"];
  F [label="app.py\\nStreamlit + Cytoscape\\n(st-link-analysis) + Plotly", fillcolor="#3b2f0b", color="#fbbf24"];
  G [label="aisstream.io\\nWebSocket AIS"];
  H [label="src/ais.py\\nsaring MMSI tersanksi"];
  A -> B -> C -> D -> E -> F;
  G -> H -> F;
}
""", use_container_width=True)
    st.markdown("""
| Modul | Yang dilakukan |
|---|---|
| `scripts/bangun_data.py` | Unduh koleksi *default* OpenSanctions, pilih benih bertopik sanksi, saring relasi, tulis CSV ringkas |
| `src/muat_data.py` | Baca CSV dengan tipe yang benar; kamus tipe entitas, jenis relasi, nama negara, bendera kemudahan |
| `src/graf.py` | Bangun `MultiDiGraph`, pencarian, ego-graf dengan prioritas, perluasan, jalur terpendek, rantai pemilik kapal, paparan, statistik |
| `src/ais.py` | Klien WebSocket aisstream.io dan pencocokan MMSI |
| `app.py` | Sidebar, enam tab, komponen Cytoscape, grafik Plotly, learning mode |
| `tests/` | Pengujian pytest atas graf buatan kecil dan atas snapshot asli |

#### Model data: FollowTheMoney
OpenSanctions memakai skema **FollowTheMoney (FtM)**. Setiap baris adalah satu entitas dengan `schema` dan `properties`.
Yang membuat analisis keterkaitan mungkin: **relasi juga entitas**. Sebuah `Ownership` punya properti `owner` dan `asset`
yang masing-masing berisi id entitas lain; `Directorship` punya `director` dan `organization`; `Family` punya `person`
dan `relative`. Skrip pembangun mengubah setiap entitas relasi menjadi satu sisi berarah `sumber -> tujuan`.

```json
{"id": "NK-...", "schema": "Ownership", "properties": {"owner": ["NK-orang"], "asset": ["NK-perusahaan"], "percentage": ["51"]}}
```

#### Mengapa Cytoscape, bukan Plotly?
Plotly bisa menggambar graf statis, tetapi tidak mengembalikan "simpul mana yang diklik" dan tidak punya tata letak
gaya (force-directed) yang dihitung di browser. Cytoscape.js dibuat untuk graf: tata letak fcose, seleksi, klik dua
kali, dan hapus simpul semuanya berjalan di sisi klien, dan `st-link-analysis` meneruskan peristiwanya ke Python.
""")
    belajar("mengulang proyek ini sendiri", """
Urutan yang disarankan kalau kamu ingin membangun ulang dari nol:

1. Unduh satu dataset kecil dulu, misalnya `us_ofac_sdn/entities.ftm.json` (±50 MB), dan hitung jumlah entitas per `schema`.
2. Ubah entitas `Ownership`/`Directorship` menjadi sisi, masukkan ke `networkx`, cetak 10 simpul berderajat tertinggi.
3. Tampilkan ego-graf satu nama dengan `st_link_analysis`; tambahkan klik simpul -> `st.session_state`.
4. Baru kemudian: pemangkasan hub, jalur terpendek, tab kapal, dan AIS.

Latihan bertingkat ada di `docs/LATIHAN.md`; penjelasan konsep di `docs/BELAJAR.md`.
""")

st.caption(DISCLAIMER)
