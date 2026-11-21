"""Water probe: times candidate sources of ditches, streams and water bodies near a parcel (see README.md here).
It writes water-probe-<host>-<UTC time>.json; only parcel centre coordinates are sent to external services."""
import concurrent.futures as cf
import io
import json
import math
import os
import struct
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

import pyarrow
import pyarrow.compute as pc
import pyarrow.parquet as pq

VERSION = "1.0.0"
RADIUS_M, REPEATS, TIMEOUT_S, ROUND_TIMEOUT_S = 500, 3, 25, 40
OVERPASS = {  # public Overpass API servers (OpenStreetMap data)
    "overpass-api.de": "https://overpass-api.de/api/interpreter",
    "overpass.private.coffee": "https://overpass.private.coffee/api/interpreter",
    "maps.mail.ru": "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "overpass.openstreetmap.fr": "https://overpass.openstreetmap.fr/api/interpreter",
}
# BDOT10k (GUGiK): one nationwide GeoParquet file per object class, rows grouped by county (TERYT).
BDOT_URL = "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GeoParquet/{}.parquet"
BDOT_CLASSES = {"OT_SWRM_L": "drainage ditch", "OT_SWRS_L": "river or stream", "OT_SWKN_L": "canal",
                "OT_PTWP_A": "surface water"}
BDOT_WMS = ("bdot10k-wms", "row,rz,kan,WPow", "text/xml",
            "https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer")
MPHP_WMS = ("mphp-wms", "19,22", "application/geojson",  # Wody Polskie: watercourse sections and lakes
            "https://wody.isok.gov.pl/gpservices/KZGW/ISOK_MPHP/MapServer/WMSServer")
WMS_REQUESTS = ((BDOT_WMS, "GetMap", 500, 500), (BDOT_WMS, "GetFeatureInfo", 500, 101), (MPHP_WMS, "GetMap", 500, 500),
                (MPHP_WMS, "GetFeatureInfo", 500, 101), (MPHP_WMS, "GetFeatureInfo", 5000, 11))  # last: 900 m pixel
DOWNLOADS = (("full download, canals", "OT_SWKN_L", None), ("first 32 MB, ditches", "OT_SWRM_L", 32 * 2 ** 20))
# Test parcels: cadastral id -> (region, lon, lat, easting and northing in EPSG:2180, county code).
PARCELS = {
    "040704_2.0020.34/2": ("kujawsko-pomorskie", 18.20085, 52.74927, 446075.2, 542924.8, "0407"),
    "022003_5.0007.170/4": ("dolnoslaskie", 17.04930, 51.35050, 364200.5, 388901.4, "0220"),
    "120805_5.0007.41": ("malopolskie", 19.95000, 50.35010, 567567.2, 276315.0, "1208"),
}

HOST, STARTED = os.environ.get("PROBE_HOST") or os.uname().nodename, datetime.now(timezone.utc)
OUT_PATH = f"water-probe-{HOST}-{STARTED:%Y%m%dT%H%M%SZ}.json"
RESULT = {"probe": "water", "version": VERSION, "started_utc": STARTED.isoformat(), "host": HOST,
          "python": sys.version.split()[0], "pyarrow": pyarrow.__version__, "radius_m": RADIUS_M,
          "finished": False, "queries": []}
LOCK, HEADERS = threading.Lock(), {"User-Agent": f"water-probe/{VERSION}"}


def save():
    RESULT["elapsed_s"] = round((datetime.now(timezone.utc) - STARTED).total_seconds(), 1)
    with open(OUT_PATH + ".tmp", "w") as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=1)
    os.replace(OUT_PATH + ".tmp", OUT_PATH)


def measure(source, description, params, fn):
    """Run one query, record timing and outcome, never raise (except on Ctrl-C)."""
    rec, t0 = {"source": source, "description": description, "params": params}, time.perf_counter()
    try:
        rec.update(ok=True, **fn())
    except Exception as exc:
        body = exc.read(600).decode("utf-8", "replace") if hasattr(exc, "read") else None
        rec.update(ok=False, http_status=getattr(exc, "code", None), error=traceback.format_exc(), error_body=body)
    rec["seconds"] = round(time.perf_counter() - t0, 3)
    with LOCK:
        RESULT["queries"].append(rec)
        save()
        print(f"[{len(RESULT['queries']):3d}] {rec['seconds']:7.2f} s  {'ok ' if rec['ok'] else 'ERR'} "
              f"{source}: {description} {json.dumps(params)}", flush=True)


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data, {**HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read(), resp.status, resp.headers.get("Content-Type")


def overpass(url, lon, lat):
    around = f"(around:{RADIUS_M},{lat},{lon})"
    query = f"[out:json][timeout:20];(way{around}[waterway];way{around}[natural=water];);out tags;"
    raw, status, _ = http(url, urllib.parse.urlencode({"data": query}).encode())
    data = json.loads(raw)
    kinds = Counter(e["tags"].get("waterway") or "water:" + e["tags"].get("water", "unspecified")
                    for e in data["elements"])
    return {"http_status": status, "bytes": len(raw), "summary": {
        "objects": len(data["elements"]), "by_type": dict(kinds),
        "osm_base": data.get("osm3s", {}).get("timestamp_osm_base"), "remark": data.get("remark")}}


class HttpFile(io.RawIOBase):  # read-only file over HTTP range requests; counts requests and bytes
    def __init__(self, url):
        self.url, self.pos, self.requests, self.bytes = url, 0, 0, 0
        head = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(head, timeout=TIMEOUT_S) as resp:
            self.size, self.modified = int(resp.headers["Content-Length"]), resp.headers.get("Last-Modified")
    readable = seekable = lambda self: True
    tell = lambda self: self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (self.pos if whence == 1 else self.size) + offset
        return self.pos

    def read(self, size=-1):
        size = self.size - self.pos if size < 0 else min(size, self.size - self.pos)
        if size <= 0:
            return b""
        data, _, _ = http(self.url, headers={"Range": f"bytes={self.pos}-{self.pos + size - 1}"})
        self.pos, self.requests, self.bytes = self.pos + len(data), self.requests + 1, self.bytes + len(data)
        return data


def wkb_rings(wkb, at=0):
    """Coordinate tuples (x, y, x, y, ...) of a little-endian 2D WKB line, polygon or multi-geometry."""
    kind, count = struct.unpack_from("<II", wkb, at + 1)
    at, rings = at + 9, []
    for _ in range(count if kind % 1000 != 2 else 1):
        if kind % 1000 in (2, 3):
            points = count if kind % 1000 == 2 else struct.unpack_from("<I", wkb, at)[0]
            at += 0 if kind % 1000 == 2 else 4
            rings.append(struct.unpack_from(f"<{2 * points}d", wkb, at))
            at += 16 * points
        else:
            sub, at = wkb_rings(wkb, at)
            rings += sub
    return rings, at


def distance_m(wkb, x, y):
    """Shortest distance from the point to any segment of the geometry (EPSG:2180, metres)."""
    best = math.inf
    for ring in wkb_rings(wkb)[0]:
        for i in range(0, len(ring) - 2, 2):
            ax, ay, dx, dy = ring[i], ring[i + 1], ring[i + 2] - ring[i], ring[i + 3] - ring[i + 1]
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
            best = min(best, math.hypot(ax + t * dx - x, ay + t * dy - y))
    return best


def bdot_class(name, x, y, county):
    """Read one object class for one county straight from the remote file, keep objects within the radius."""
    remote = HttpFile(BDOT_URL.format(name))
    parquet, t0 = pq.ParquetFile(remote), time.perf_counter()
    meta, columns = parquet.metadata, parquet.schema_arrow.names
    stats = [meta.row_group(i).column(columns.index("TERYT")).statistics for i in range(meta.num_row_groups)]
    candidates = [i for i, s in enumerate(stats) if s.min <= county <= s.max]
    groups = [i for i in candidates
              if pc.any(pc.equal(parquet.read_row_group(i, columns=["TERYT"])["TERYT"], county)).as_py()]
    t_index, in_county, near = time.perf_counter() - t0, 0, []
    wanted = ["TERYT", "GEOM"] + [c for c in ("RODZAJ", "NAZWA", "WERSJA") if c in columns]
    for i in groups:
        table = parquet.read_row_group(i, columns=wanted).filter(pc.field("TERYT") == county)
        in_county += table.num_rows
        for row in table.to_pylist():
            dist = distance_m(row["GEOM"], x, y)
            if dist <= RADIUS_M:
                near.append({"distance_m": round(dist), "kind": row.get("RODZAJ"), "name": row.get("NAZWA"),
                             "version": str(row.get("WERSJA"))[:10]})
    near.sort(key=lambda n: n["distance_m"])
    return {"http_status": 200, "bytes": remote.bytes, "objects": near, "summary": {
        "objects": len(near), "nearest_m": near[0]["distance_m"] if near else None, "objects_in_county": in_county,
        "http_requests": remote.requests, "file_bytes": remote.size, "file_modified": remote.modified,
        "row_groups": meta.num_row_groups, "row_groups_candidate": len(candidates), "row_groups_read": len(groups),
        "seconds_finding_groups": round(t_index, 3)}}


def bdot_all(x, y, county):
    with cf.ThreadPoolExecutor(max_workers=len(BDOT_CLASSES)) as pool:
        parts = dict(zip(BDOT_CLASSES, pool.map(lambda name: bdot_class(name, x, y, county), BDOT_CLASSES)))
    return {"http_status": 200, "bytes": sum(p["bytes"] for p in parts.values()),
            "summary": {name: p["summary"]["objects"] for name, p in parts.items()}}


def download(name, limit):
    """Download a whole file, or its first `limit` bytes, to estimate the time of a full nationwide fetch."""
    url, t0 = BDOT_URL.format(name), time.perf_counter()
    raw, status, _ = http(url, headers={"Range": f"bytes=0-{limit - 1}"} if limit else None)
    return {"http_status": status, "bytes": len(raw),
            "summary": {"megabytes_per_s": round(len(raw) / 1e6 / (time.perf_counter() - t0), 2)}}


def wms(base, layers, request, x, y, half_m, pixels, info_format):
    """GetMap, or GetFeatureInfo at the centre pixel, for a square window around the point."""
    params = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": request, "LAYERS": layers,
              "STYLES": "," * layers.count(","), "SRS": "EPSG:2180", "WIDTH": pixels, "HEIGHT": pixels,
              "BBOX": f"{x - half_m},{y - half_m},{x + half_m},{y + half_m}",
              "FORMAT": "image/png", "TRANSPARENT": "TRUE"}
    if request == "GetFeatureInfo":
        params.update(QUERY_LAYERS=layers, X=pixels // 2, Y=pixels // 2, INFO_FORMAT=info_format, FEATURE_COUNT=50)
    raw, status, ctype = http(base + "?" + urllib.parse.urlencode(params))
    summary = {"content_type": ctype}
    if request == "GetMap":
        if not raw.startswith(b"\x89PNG"):
            raise RuntimeError("not an image: " + raw[:600].decode("utf-8", "replace"))
    elif info_format == "application/geojson":
        features = json.loads(raw)["features"]
        summary.update(objects=len(features), with_geometry=sum(bool(f.get("geometry")) for f in features),
                       names=sorted({str(f["properties"].get("Nazwarzeki")) for f in features})[:10])
    else:
        summary.update(objects=raw.count(b"<FIELDS"), sample=raw[:600].decode("utf-8", "replace"))
    return {"http_status": status, "bytes": len(raw), "summary": summary}


def probe_parcel(parcel_id, region, lon, lat, x, y, county, rep):
    base = {"parcel": parcel_id, "region": region, "repeat": rep}
    # Overpass servers are independent hosts: ask them at the same time, each with its own timeout.
    pool = cf.ThreadPoolExecutor(max_workers=len(OVERPASS))
    futures = [pool.submit(measure, f"overpass:{name}", f"waters within {RADIUS_M} m", base,
                           lambda url=url: overpass(url, lon, lat)) for name, url in OVERPASS.items()]
    cf.wait(futures, timeout=ROUND_TIMEOUT_S)
    pool.shutdown(wait=False, cancel_futures=True)
    for name, label in BDOT_CLASSES.items():
        measure("bdot10k-geoparquet", f"remote read, {label}, within {RADIUS_M} m",
                {**base, "class": name, "county": county}, lambda: bdot_class(name, x, y, county))
    measure("bdot10k-geoparquet", "remote read, all classes in parallel", {**base, "county": county},
            lambda: bdot_all(x, y, county))
    for (source, layers, info_format, url), request, half_m, pixels in WMS_REQUESTS:
        measure(source, f"{request}, {2 * half_m} m window, {pixels} px", {**base, "layers": layers},
                lambda: wms(url, layers, request, x, y, half_m, pixels, info_format))


def main():
    print(f"water probe {VERSION} on {HOST}; result file: {OUT_PATH}", flush=True)
    try:
        for rep in range(1, REPEATS + 1):
            for parcel_id, parcel in PARCELS.items():
                probe_parcel(parcel_id, *parcel, rep)
            for description, name, limit in DOWNLOADS:
                measure("bdot10k-geoparquet", description, {"class": name, "repeat": rep, "limit_bytes": limit},
                        lambda: download(name, limit))
        RESULT["finished"] = True
    except KeyboardInterrupt:
        RESULT["interrupted"] = True
    finally:
        with LOCK:
            save()
        if os.geteuid() == 0:  # in Docker: hand the file to the owner of the directory
            os.chown(OUT_PATH, os.stat(".").st_uid, os.stat(".").st_gid)
        print(f"done in {RESULT['elapsed_s']} s; result file: {OUT_PATH}", flush=True)
        os._exit(0)  # do not wait for Overpass requests that are still hanging


if __name__ == "__main__":
    main()
