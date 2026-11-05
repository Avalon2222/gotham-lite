"""
src/ais.py - mencocokkan kapal tersanksi dengan siaran AIS langsung (aisstream.io)
====================================================================================
AIS (Automatic Identification System) adalah sinyal radio yang wajib dipancarkan kapal besar:
identitas (MMSI), posisi, kecepatan, haluan. aisstream.io meneruskan sinyal yang ditangkap ribuan
penerima sukarelawan lewat WebSocket, gratis dengan kunci API.

Ide tab "Live AIS": ambil semua MMSI kapal yang ada di daftar sanksi (dari data/simpul.csv.gz),
dengarkan siaran dunia selama beberapa puluh detik, dan tampilkan kapal tersanksi yang saat itu
sedang memancarkan posisinya. aisstream membatasi filter MMSI per langganan, sedangkan kapal
tersanksi ada ratusan, sehingga yang dilakukan: berlangganan seluruh dunia lalu menyaring di sisi
klien. Kapal yang mematikan AIS (praktik umum "armada bayangan") tentu tidak akan muncul; itu
sendiri sebuah temuan.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import pandas as pd

URL_STREAM = "wss://stream.aisstream.io/v0/stream"
SELURUH_DUNIA = [[[-90.0, -180.0], [90.0, 180.0]]]
TIPE_PESAN = ["PositionReport", "StandardClassBPositionReport"]
DURASI_DEFAULT = 30
KOLOM = ["mmsi", "nama_ais", "lat", "lon", "sog_knot", "cog", "status_nav", "waktu_pesan"]

STATUS_NAV = {0: "berlayar dengan mesin", 1: "berlabuh jangkar", 2: "tidak terkendali", 3: "olah gerak terbatas",
              4: "terbatas sarat", 5: "tertambat", 6: "kandas", 7: "menangkap ikan", 8: "berlayar dengan layar",
              15: "tidak ditentukan"}


class AisError(RuntimeError):
    """Gagal terhubung atau tidak menerima pesan dari aisstream.io."""


def ambil_api_key() -> str | None:
    """Kunci API dari variabel lingkungan ``AISSTREAM_API_KEY`` (app.py mengisinya dari st.secrets)."""
    kunci = os.environ.get("AISSTREAM_API_KEY", "").strip()
    return kunci or None


def pesan_langganan(api_key: str, bounding_boxes=None, tipe_pesan=None, mmsi: list[str] | None = None) -> dict:
    """Pesan pertama ke server: wilayah, jenis pesan, dan (opsional) daftar MMSI yang disaring server."""
    pesan = {
        "APIKey": api_key,
        "BoundingBoxes": bounding_boxes or SELURUH_DUNIA,
        "FilterMessageTypes": tipe_pesan or TIPE_PESAN,
    }
    if mmsi:
        pesan["FiltersShipMMSI"] = [str(m) for m in mmsi]
    return pesan


def _angka(v, default=None):
    try:
        if v is None:
            return default
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _waktu_meta(meta: dict):
    """``time_utc`` aisstream berbentuk '2024-01-01 12:34:56.123456789 +0000 UTC'; ambil detiknya saja."""
    teks = str(meta.get("time_utc", ""))[:19]
    try:
        return pd.Timestamp(teks, tz="UTC")
    except (ValueError, TypeError):
        return None


def urai_posisi(pesan: dict) -> dict | None:
    """Satu pesan aisstream -> baris posisi, atau None bila bukan laporan posisi yang valid.

    Nilai "tidak tersedia" menurut standar AIS (SOG 102,3; COG 360; lat 91; lon 181) diubah
    menjadi None agar tidak merusak peta.
    """
    tipe = pesan.get("MessageType")
    if tipe not in TIPE_PESAN:
        return None
    meta = pesan.get("MetaData") or {}
    isi = (pesan.get("Message") or {}).get(tipe) or {}
    mmsi = meta.get("MMSI") or isi.get("UserID")
    if not mmsi:
        return None
    lat = _angka(isi.get("Latitude", meta.get("latitude")))
    lon = _angka(isi.get("Longitude", meta.get("longitude")))
    if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
        return None
    sog = _angka(isi.get("Sog"))
    cog = _angka(isi.get("Cog"))
    status = _angka(isi.get("NavigationalStatus")) if tipe == "PositionReport" else None
    return {
        "mmsi": str(mmsi),
        "nama_ais": str(meta.get("ShipName") or "").replace("@", "").strip(),
        "lat": lat,
        "lon": lon,
        "sog_knot": None if sog is None or sog >= 102.3 else sog,
        "cog": None if cog is None or cog >= 360 else cog,
        "status_nav": STATUS_NAV.get(int(status), f"kode {int(status)}") if status is not None else "",
        "waktu_pesan": _waktu_meta(meta),
    }


def dengarkan(api_key: str, mmsi_target: set[str], durasi: int = DURASI_DEFAULT,
              maks_pesan: int = 400_000) -> tuple[pd.DataFrame, int, int]:
    """Dengarkan siaran AIS dunia selama ``durasi`` detik; simpan posisi terakhir kapal dalam ``mmsi_target``.

    Mengembalikan (DataFrame kapal target yang terdengar, jumlah pesan diterima, jumlah MMSI unik terdengar).
    """
    try:
        from websockets.exceptions import WebSocketException
        from websockets.sync.client import connect
    except ImportError as exc:  # pragma: no cover
        raise AisError("Paket 'websockets' belum terpasang.") from exc

    target = {str(m) for m in mmsi_target if str(m).strip()}
    posisi: dict[str, dict] = {}
    terdengar: set[str] = set()
    jumlah = 0
    batas = time.monotonic() + durasi
    try:
        with connect(URL_STREAM, compression="deflate", open_timeout=15, close_timeout=3) as ws:
            ws.send(json.dumps(pesan_langganan(api_key)))
            while True:
                sisa = batas - time.monotonic()
                if sisa <= 0 or jumlah >= maks_pesan:
                    break
                try:
                    mentah = ws.recv(timeout=min(sisa, 5))
                except TimeoutError:
                    continue
                try:
                    pesan = json.loads(mentah)
                except json.JSONDecodeError:
                    continue
                if "error" in pesan and "MessageType" not in pesan:
                    raise AisError(f"aisstream.io menolak: {pesan['error']}")
                jumlah += 1
                meta = pesan.get("MetaData") or {}
                mmsi = str(meta.get("MMSI") or "")
                terdengar.add(mmsi)
                if mmsi not in target:
                    continue
                baris = urai_posisi(pesan)
                if baris:
                    posisi[mmsi] = baris
    except AisError:
        raise
    except (WebSocketException, OSError, TimeoutError) as exc:
        if jumlah == 0:
            raise AisError(f"Tidak dapat terhubung ke aisstream.io ({type(exc).__name__}: {exc}).") from exc
    if jumlah == 0:
        raise AisError("Terhubung, tetapi tidak ada pesan diterima. Kunci API mungkin salah atau kuota habis.")
    return ke_dataframe(posisi), jumlah, len(terdengar)


def ke_dataframe(posisi: dict[str, dict]) -> pd.DataFrame:
    if not posisi:
        return pd.DataFrame(columns=KOLOM)
    df = pd.DataFrame(list(posisi.values()), columns=KOLOM)
    df["waktu_pesan"] = pd.to_datetime(df["waktu_pesan"], utc=True, errors="coerce")
    return df.sort_values("mmsi").reset_index(drop=True)


def gabung_dengan_kapal(df_posisi: pd.DataFrame, kapal: pd.DataFrame) -> pd.DataFrame:
    """Sandingkan posisi AIS dengan data kapal tersanksi (nama di daftar, bendera, IMO, program)."""
    if df_posisi.empty:
        return df_posisi
    k = kapal[kapal["mmsi"] != ""][["mmsi", "nama", "bendera", "imo", "program", "jenis_kapal", "id"]]
    k = k.drop_duplicates("mmsi")
    return df_posisi.merge(k, on="mmsi", how="left")


def sekarang_utc() -> datetime:
    return datetime.now(timezone.utc)
