"""Terrain probe: times every known way to get parcel elevation (GUGiK WCS in several request forms, GUGiK
point-height service, GUGiK 1 m sheet files, Copernicus DEM 30 m) and compares the terrain figures. Run it with the
Docker command from scripts/probes/README.md; it writes terrain-probe-<host>-<UTC time>.json to the current directory.
"""
import concurrent.futures as cf
import json
import os
import re
import tempfile
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timezone

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

VERSION = "1.0.0"
REPEATS, WCS_TIMEOUT_S, HTTP_TIMEOUT_S, WCS_THREADS, BUFFER_M = 3, 90, 60, 36, 30
API_PLAN = (("GET", 400, 5), ("POST", 1000, 5), ("POST", 1000, 2), ("POST", 100000, 5))  # the last one is oversized
GUGIK = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/"
WCS_TIFF, WCS_ASC = GUGIK + "NMT/GRID1/WCS/DigitalTerrainModelFormatTIFF", GUGIK + "NMT/GRID1/WCS/DigitalTerrainModel"
TIFF_ID, ASC_ID, CRS_URI = "DTM_PL-KRON86-NH_TIFF", "DTM_PL-EVRF2007-NH", "http://www.opengis.net/def/crs/EPSG/0/2180"
V2 = f"{WCS_TIFF}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID={TIFF_ID}&FORMAT=image/tiff"
V2_EN = V2 + "&SUBSET=x({e0},{e1})&SUBSET=y({n0},{n1})"
V1 = "?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&CRS=EPSG:2180&RESPONSE_CRS=EPSG:2180&COVERAGE="
T1, EN_BOX = f"{WCS_TIFF}{V1}{TIFF_ID}&FORMAT=image/tiff", "&BBOX={e0},{n0},{e1},{n1}&WIDTH={w}&HEIGHT={h}"
WCS_FORMS = {  # every GetCoverage form considered possible; e = easting, n = northing, w, h = window size in metres
    "2.0.1 subset x=easting y=northing": V2_EN,
    "2.0.1 subset x=northing y=easting": V2 + "&SUBSET=x({n0},{n1})&SUBSET=y({e0},{e1})",
    "2.0.1 subset with subsetting and output CRS": f"{V2_EN}&SUBSETTINGCRS={CRS_URI}&OUTPUTCRS={CRS_URI}",
    "2.0.1 subset with SCALEFACTOR=0.2": V2_EN + "&SCALEFACTOR=0.2",
    "1.0.0 bbox easting,northing (geoportal sample form)": T1 + EN_BOX,
    "ascii-grid service, 1.0.0 bbox easting,northing (geoportal sample form)":
        f"{WCS_ASC}{V1}{ASC_ID}&FORMAT=image/x-aaigrid" + EN_BOX}
SHEET_INDEX, INDEX_YEARS = GUGIK + "NumerycznyModelTerenuEVRF2007/WFS/Skorowidze", range(2018, 2027)
HEIGHT_API, STAC_SEARCH = "https://services.gugik.gov.pl/nmt/", "https://earth-search.aws.element84.com/v1/search"
PARCELS = {  # test parcels: cadastral id -> (region, simplified outline as lon/lat ring)
    "040704_2.0020.34/2": ("kujawsko-pomorskie, 2.5 ha", [
        [18.202447, 52.749197], [18.200317, 52.750263], [18.199112, 52.749417], [18.201061, 52.748485],
        [18.201620, 52.748218], [18.202447, 52.749197]]),
    "022003_5.0007.170/4": ("dolnoslaskie, 5 ha", [
        [17.048244, 51.349763], [17.049458, 51.349477], [17.050788, 51.349393], [17.051103, 51.351404],
        [17.047432, 51.351590], [17.047540, 51.351149], [17.048244, 51.349763]]),
    "120805_5.0007.41": ("malopolskie, 1.3 ha, 40 m wide strip", [
        [19.949403, 50.348508], [19.950044, 50.348444], [19.950161, 50.349324], [19.950431, 50.350752],
        [19.950609, 50.351692], [19.949963, 50.351734], [19.949564, 50.349414], [19.949403, 50.348508]])}

HOST = os.environ.get("PROBE_HOST") or os.uname().nodename
STARTED, LOCK = datetime.now(timezone.utc), threading.Lock()
OUT_PATH = f"terrain-probe-{HOST}-{STARTED:%Y%m%dT%H%M%SZ}.json"
RESULT = {"probe": "terrain", "version": VERSION, "started_utc": STARTED.isoformat(), "host": HOST,
          "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__, "buffer_m": BUFFER_M,
          "wcs_threads": WCS_THREADS, "finished": False, "queries": []}


def save():
    RESULT["elapsed_s"] = round((datetime.now(timezone.utc) - STARTED).total_seconds(), 1)
    with open(OUT_PATH + ".tmp", "w") as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=1)
    os.replace(OUT_PATH + ".tmp", OUT_PATH)


def measure(source, description, params, fn):
    """Run one query, record timing and outcome, never raise (except on Ctrl-C). Thread-safe."""
    rec = {"source": source, "description": description, "params": params}
    t0, value = time.perf_counter(), None
    try:
        value, info = fn()
        rec.update(ok=True, **info)
    except Exception as exc:
        body = exc.read()[:600].decode("utf-8", "replace") if hasattr(exc, "read") else None  # HTTP error text
        rec.update(ok=False, http_status=getattr(exc, "code", None), error_body=body, error=traceback.format_exc())
    rec["seconds"] = round(time.perf_counter() - t0, 3)
    with LOCK:
        RESULT["queries"].append(rec)
        save()
        print(f"[{len(RESULT['queries']):3d}] {rec['seconds']:7.2f} s  {'ok ' if rec['ok'] else 'ERR'} {source}: "
              f"{description} {json.dumps({k: v for k, v in params.items() if k != 'url'})}", flush=True)
    return value


def http(url, data=None, timeout=HTTP_TIMEOUT_S, headers=None):
    """GET (or POST when data is given) with a limit on the whole exchange. Returns (body, info)."""
    req = urllib.request.Request(url, data, {"User-Agent": f"terrain-probe/{VERSION}", **(headers or {})})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        first, body = round(time.perf_counter() - t0, 3), b""
        while (chunk := resp.read(1 << 20)) and time.perf_counter() - t0 < timeout:
            body += chunk
        if chunk:
            raise TimeoutError(f"response not complete within {timeout} s")
        return body, {"http_status": resp.status, "bytes": len(body), "first_byte_s": first,
                      "content_type": resp.headers.get("Content-Type")}


def summarize(e, n, z, parcel):
    """Least-squares plane (slope, downslope direction, relief) for the window and for the points in the parcel."""
    e, n, z = (np.asarray(v, float).ravel() for v in (e, n, z))
    valid, hit, ring, out = np.isfinite(z) & (z > -500), np.zeros(z.shape, bool), parcel["ring_en"], {}
    for (e1, n1), (e2, n2) in zip(ring, ring[1:]):  # ray casting
        if n1 != n2:
            hit ^= ((n1 > n) != (n2 > n)) & (e < (e2 - e1) * (n - n1) / (n2 - n1) + e1)
    for name, m in (("window", valid), ("parcel", valid & hit)):
        out[name] = {"points": int(m.sum())}
        if m.sum() >= 3:
            design = np.column_stack([e[m] - e[m].mean(), n[m] - n[m].mean(), np.ones(m.sum())])
            coef, low = np.linalg.lstsq(design, z[m], rcond=None)[0], int(z[m].argmin())
            out[name].update(
                min_m=round(float(z[m].min()), 2), max_m=round(float(z[m].max()), 2), mean_m=round(float(z[m].mean()), 2),
                slope_pct=round(float(np.hypot(coef[0], coef[1])) * 100, 3),
                downslope_azimuth_deg=round(float(np.degrees(np.arctan2(-coef[0], -coef[1]))) % 360, 1),
                rms_off_plane_m=round(float(np.sqrt(np.mean((design @ coef - z[m]) ** 2))), 3),
                lowest_point_en=[round(float(e[m][low]), 1), round(float(n[m][low]), 1)])
    return out


def grid_points(src, box=None):
    """Pixel centres and values of a north-up raster (path, URL or bytes), optionally cut to box (W, S, E, N)."""
    if isinstance(src, bytes):  # GDAL picks the driver from the file name, so write the bytes out first
        with tempfile.NamedTemporaryFile(suffix=".asc" if src[:5].lower() == b"ncols" else ".tif", buffering=0) as tmp:
            tmp.write(src)
            return grid_points(tmp.name, box)
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT=20), \
            rasterio.open(src) as ds:
        win = None
        if box:
            (r0, c0), (r1, c1) = ds.index(box[0], box[3]), ds.index(box[2], box[1])
            r0, c0, r1, c1 = max(r0, 0), max(c0, 0), min(r1, ds.height - 1), min(c1, ds.width - 1)
            win = Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
        z, t = ds.read(1, window=win).astype(float), ds.window_transform(win) if win else ds.transform
        if ds.nodata is not None:
            z[z == ds.nodata] = np.nan
        cols, rows = np.meshgrid(np.arange(z.shape[1]) + 0.5, np.arange(z.shape[0]) + 0.5)
        return t.c + cols * t.a, t.f + rows * t.e, z, {"shape": list(z.shape), "file_shape": list(ds.shape),
                                                       "crs": str(ds.crs), "pixel": list(ds.res), "dtype": ds.dtypes[0]}


def fetch_coverage(url, parcel, timeout):
    """One WCS request; a raster answer is summarised, a service exception becomes an error."""
    body, info = http(url, timeout=timeout)
    if body[:4] in (b"II*\x00", b"MM\x00*") or body[:5].lower() == b"ncols":
        e, n, z, info["raster"] = grid_points(body)
        info["summary"] = summarize(e, n, z, parcel)
    elif b"Exception" in body[:600]:
        raise RuntimeError(body[:600].decode("utf-8", "replace"))
    else:
        info["summary"] = body[:160].decode("utf-8", "replace")
    return None, info


def wcs_round(parcels, rep):
    """All WCS requests of one repeat, in parallel, so that hanging ones do not add up."""
    tasks = [("service check: GetCoverage outside the coverage (a quick error is expected)", {"repeat": rep},
              V2_EN.format(e0=10, n0=10, e1=20, n1=20), parcels[0], 30)]
    for i, p in enumerate(parcels):
        e0, n0, e1, n1 = p["bbox"]
        ce, cn, boxes = (e0 + e1) // 2, (n0 + n1) // 2, {f"parcel window {e1 - e0}x{n1 - n0} m": p["bbox"]}
        if i == 0:  # window-size variants around the centre of the first parcel
            boxes.update({f"{s}x{s} m": (ce - s // 2, cn - s // 2, ce + s // 2, cn + s // 2) for s in (100, 1000)})
        tasks += [(f"GetCoverage {label}", {"parcel": p["id"], "window": size, "repeat": rep},
                   form.format(e0=b[0], n0=b[1], e1=b[2], n1=b[3], w=b[2] - b[0], h=b[3] - b[1]), p, WCS_TIMEOUT_S)
                  for size, b in boxes.items() for label, form in WCS_FORMS.items()]
    with cf.ThreadPoolExecutor(max_workers=WCS_THREADS) as pool:
        list(pool.map(lambda t: measure("gugik-wcs", t[0], {**t[1], "url": t[2]},
                                        lambda: fetch_coverage(t[2], t[3], t[4])), tasks))


def height_api(parcel, method, batch, step):
    """Heights on a regular grid from the point-height service (x = northing, y = easting)."""
    e0, n0, e1, n1 = parcel["bbox"]
    pts = [f"{n} {e}" for n in range(n0, n1 + 1, step) for e in range(e0, e1 + 1, step)]
    query = lambda c: "request=GetHByPointList&list=" + ",".join(c).replace(" ", "%20")
    call = lambda c: http(HEIGHT_API, query(c).encode()) if method == "POST" else http(f"{HEIGHT_API}?{query(c)}")
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        parts = list(pool.map(call, [pts[i:i + batch] for i in range(0, len(pts), batch)]))
    text = ",".join(body.decode("utf-8", "replace") for body, _ in parts)
    rows = [r for r in (p.split() for p in text.split(",")) if len(r) == 3]
    if not rows:
        raise RuntimeError(f"asked for {len(pts)} points, no heights in the answer: {text[:300]}")
    good = np.array([r for r in rows if float(r[2]) != 0], float)  # a failed request answers 0.0 for every point
    return None, {"http_status": 200, "bytes": len(text), "requests": len(parts), "points": len(pts),
                  "rows_without_height": len(pts) - len(rows), "zero_heights": len(rows) - len(good),
                  "summary": summarize(*good.reshape(-1, 3).T[[1, 0, 2]], parcel)}


def sheets(parcel):
    """Find 1 m sheet files in the WFS index, download the most accurate one per sheet whole, cut the window out."""
    e0, n0, e1, n1 = parcel["bbox"]
    url, t0 = (f"{SHEET_INDEX}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&COUNT=50&BBOX={n0},{e0},{n1},{e1},"
               "urn:ogc:def:crs:EPSG::2180&TYPENAMES=gugik:SkorowidzNMT"), time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=len(INDEX_YEARS)) as pool:
        pages = [body.decode("utf-8", "replace") for body, _ in pool.map(lambda y: http(f"{url}{y}"), INDEX_YEARS)]
    listed = [dict(re.findall(r"<gugik:(\w+)>([^<]*)</gugik:", member))
              for page in pages for member in re.findall(r"<wfs:member>(.*?)</wfs:member>", page, re.S)]
    grids = [s for s in listed if s.get("format") == "ARC/INFO ASCII GRID" and s.get("char_przestrz") == "1.00 m"]
    grids.sort(key=lambda s: (-float(s["blad_sr_wys"]), int(s["akt_rok"])))  # the last one per sheet wins below
    chosen, t1 = list({s["godlo"]: s for s in grids}.values()), time.perf_counter()
    bodies, t2 = [http(s["url_do_pobrania"], timeout=WCS_TIMEOUT_S)[0] for s in chosen], time.perf_counter()
    parts = [grid_points(body, parcel["bbox"]) for body in bodies]
    e, n, z = (np.concatenate([p[i].ravel() for p in parts]) for i in range(3))
    return None, {"http_status": 200, "bytes": sum(map(len, bodies)), "index_s": round(t1 - t0, 3),
                  "download_s": round(t2 - t1, 3), "cut_s": round(time.perf_counter() - t2, 3), "listed": listed,
                  "chosen": chosen, "raster": parts[0][3], "summary": summarize(e, n, z, parcel)}


def dem30(parcel):
    """Find the 30 m tile in the catalogue and read the window straight from the cloud-optimised file."""
    query = {"collections": ["cop-dem-glo-30"], "intersects": {"type": "Polygon", "coordinates": [parcel["ring"]]}}
    t0 = time.perf_counter()
    raw, info = http(STAC_SEARCH, json.dumps(query).encode(), headers={"Content-Type": "application/json"})
    href, t1 = json.loads(raw)["features"][0]["assets"]["data"]["href"], time.perf_counter()
    (lons, lats), pad = zip(*parcel["ring"]), BUFFER_M / 60000  # metres to degrees, roughly
    x, y, z, raster = grid_points(href, (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad))
    e, n = warp_transform("EPSG:4326", "EPSG:2180", x.ravel().tolist(), y.ravel().tolist())
    return None, {**info, "search_s": round(t1 - t0, 3), "read_s": round(time.perf_counter() - t1, 3), "file": href,
                  "raster": raster, "summary": summarize(e, n, z, parcel)}


def main():
    print(f"terrain probe {VERSION} on {HOST}; result file: {OUT_PATH}", flush=True)
    parcels = []
    for parcel_id, (region, ring) in PARCELS.items():
        es, ns = warp_transform("EPSG:4326", "EPSG:2180", *map(list, zip(*ring)))
        bbox = (int(min(es)) - BUFFER_M, int(min(ns)) - BUFFER_M, int(max(es)) + BUFFER_M, int(max(ns)) + BUFFER_M)
        parcels.append({"id": parcel_id, "region": region, "ring": ring, "ring_en": list(zip(es, ns)), "bbox": bbox})
    try:
        for rep in range(1, REPEATS + 1):
            wcs_round(parcels, rep)
            for p in parcels:
                base, (e0, n0, e1, n1) = {"parcel": p["id"], "region": p["region"], "repeat": rep}, p["bbox"]
                url = list(WCS_FORMS.values())[-1].format(e0=e0, n0=n0, e1=e1, n1=n1, w=e1 - e0, h=n1 - n0)
                measure("gugik-wcs", "GetCoverage ascii-grid service, geoportal sample form, with no other WCS request "
                        "running", {**base, "url": url}, lambda: fetch_coverage(url, p, 30))
                for method, batch, step in API_PLAN:
                    measure("gugik-height-api", f"GetHByPointList, {method}, {batch} points per request, {step} m grid",
                            {**base, "method": method, "step_m": step}, lambda: height_api(p, method, batch, step))
                measure("gugik-sheets", "sheet index (WFS), whole 1 m sheet file(s), window cut", base, lambda: sheets(p))
                measure("copernicus-30m", "catalogue search and window read", base, lambda: dem30(p))
        RESULT["finished"] = True
    finally:  # the file is complete also after Ctrl-C or an unexpected error
        save()
        print(f"done in {RESULT['elapsed_s']} s; result file: {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
