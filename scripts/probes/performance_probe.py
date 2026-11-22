"""Performance probe: times the main data sources of one parcel analysis for ten parcels, one source after another
and all at the same time, and optionally whole analyses through a running API (its address is the only argument).
Run it with the Docker command from scripts/probes/README.md; it writes performance-probe-<host>-<UTC time>.json.
Only parcel identifiers, coordinates and dates are sent to external services."""
import concurrent.futures as cf
import json
import os
import sys
import threading
import time
import traceback
import urllib.request
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import rasterio
import rasterio.mask
from rasterio.io import MemoryFile
from rasterio.warp import transform as warp, transform_geom

VERSION = "1.0.0"
ANALYSIS_DATE, CROP, REPEATS, TIMEOUT_S, AT_ONCE, MAX_POINTS = date(2026, 6, 20), "winter_wheat", 2, 30, 3, 4000
ULDK, METEO = "https://uldk.gugik.gov.pl/", "https://archive-api.open-meteo.com/v1/archive"
IUNG, IUNG_LAYER = "https://sgeo.iung.pl/geoserver/ows", "Susza:katgl_landuse2024"
ISRIC_WCS, HEIGHT_API = "https://maps.isric.org/mapserv", "https://services.gugik.gov.pl/nmt/"
IGH, IGH_URI = "+proj=igh +datum=WGS84 +no_defs +towgs84=0,0,0", "http://www.opengis.net/def/crs/EPSG/0/152160"
SOIL, DEPTHS = ("sand", "silt", "clay", "soc"), ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm")
PC, BANDS = "https://planetarycomputer.microsoft.com/api/", ("B04", "B08", "B8A", "B11")
SCENES_NOW, SCENES_PER_YEAR, YEARS_BACK = 6, 2, 5  # scenes read with all bands: current window, each earlier year
GDAL = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_TIMEOUT": 20, "GDAL_HTTP_CONNECTTIMEOUT": 10}
PARCELS = {  # cadastral id (its first two digits are the voivodeship code) -> lon, lat of a point inside the parcel
    "220404_2.0003.101/1": (18.736273, 54.286577), "120611_5.0008.980": (19.755286, 49.944060),
    "061605_2.0005.88": (21.766298, 51.634105), "142604_2.0025.73": (22.129468, 52.303266),
    "320904_2.0061.127/4": (16.475787, 54.134072), "040308_5.0004.17198": (18.219279, 53.048308),
    "200602_2.0025.88": (22.232787, 53.439494), "160704_2.0004.566/3": (17.494249, 50.519104),
    "280502_2.0013.71": (22.517296, 53.781163), "260504_5.0004.33": (20.209625, 51.074737)}

HOST, STARTED = os.environ.get("PROBE_HOST") or os.uname().nodename, datetime.now(timezone.utc)
API = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else None
OUT_PATH = f"performance-probe-{HOST}-{STARTED:%Y%m%dT%H%M%SZ}.json"
RESULT = {"probe": "performance", "version": VERSION, "started_utc": STARTED.isoformat(), "host": HOST, "api": API,
          "cpus": os.cpu_count(), "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
          "analysis_date": str(ANALYSIS_DATE), "repeats": REPEATS, "finished": False, "queries": []}
LOCK, UA = threading.Lock(), {"User-Agent": f"performance-probe/{VERSION}"}


def save():
    RESULT["elapsed_s"] = round((datetime.now(timezone.utc) - STARTED).total_seconds(), 1)
    with open(OUT_PATH + ".tmp", "w") as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=1)
    os.replace(OUT_PATH + ".tmp", OUT_PATH)


def measure(source, description, params, fn):
    """Run one query, record timing and outcome, never raise (except on Ctrl-C). Thread-safe."""
    rec, t0 = {"source": source, "description": description, "params": params}, time.perf_counter()
    try:
        rec.update(ok=True, **fn())
    except Exception as exc:
        body = exc.read(600).decode("utf-8", "replace") if hasattr(exc, "read") else None  # HTTP error text
        rec.update(ok=False, http_status=getattr(exc, "code", None), error=traceback.format_exc(), error_body=body,
                   retry_after=exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None)
    rec["seconds"] = round(time.perf_counter() - t0, 3)
    with LOCK:
        RESULT["queries"].append(rec)
        save()
        print(f"[{len(RESULT['queries']):3d}] {rec['seconds']:7.2f} s  {'ok ' if rec['ok'] else 'ERR'} {source}: "
              f"{description} {json.dumps(params)}", flush=True)
    return rec


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data, {**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read(), resp.status, resp.headers


def pmap(fn, items, workers):
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def out(status, size, **summary):
    return {"http_status": status, "bytes": size, "summary": summary}


def set_outline(p, ring):
    """Derived geometry of a parcel: outline in EPSG:2180, its box with a 30 m margin, a 5 x 5 grid of points."""
    lons, lats = zip(*ring)
    es, ns = warp("EPSG:4326", "EPSG:2180", list(lons), list(lats))
    box = (int(min(es)) - 30, int(min(ns)) - 30, int(max(es)) + 30, int(max(ns)) + 30)
    part = lambda lo, hi, i: lo + (hi - lo) * (0.1 + 0.2 * i)
    grid = [(part(min(lons), max(lons), i), part(min(lats), max(lats), j)) for i in range(5) for j in range(5)]
    p.update(ring=ring, box=box, grid=grid, geom={"type": "Polygon", "coordinates": [ring]})


def uldk(p):
    query = {"request": "GetParcelById", "id": p["id"], "srid": "4326",
             "result": "id,voivodeship,county,commune,region,parcel,geom_wkt"}
    raw, status, _ = http(f"{ULDK}?{urlencode(query)}")
    lines = raw.decode("utf-8", "replace").splitlines()
    if lines[0].split()[0] != "0":
        raise RuntimeError(f"unexpected answer: {raw[:300]!r}")
    outer = lines[1].split("((")[1].lstrip("(").split(")")[0]  # outer ring of the first polygon of the EWKT
    ring = [[float(v) for v in point.split()[:2]] for point in outer.split(",")]
    set_outline(p, ring)
    return out(status, len(raw), outline_points=len(ring))


def weather(p):
    start = date(ANALYSIS_DATE.year - 10, 1, 1) - timedelta(days=120)
    query = {"latitude": p["lat"], "longitude": p["lon"], "start_date": start, "end_date": ANALYSIS_DATE,
             "timezone": "Europe/Warsaw", "daily": "precipitation_sum,et0_fao_evapotranspiration"}
    raw, status, head = http(f"{METEO}?{urlencode(query)}")
    return out(status, len(raw), days=len(json.loads(raw)["daily"]["time"]), cost=head.get("X-RateLimit-Cost"))


def soil_iung(p):
    def one(point):
        lon, lat = point
        query = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo", "LAYERS": IUNG_LAYER, "STYLES": "",
                 "QUERY_LAYERS": IUNG_LAYER, "SRS": "EPSG:4326", "WIDTH": 3, "HEIGHT": 3, "X": 1, "Y": 1,
                 "BBOX": f"{lon - 5e-5},{lat - 5e-5},{lon + 5e-5},{lat + 5e-5}", "INFO_FORMAT": "application/json"}
        raw = http(f"{IUNG}?{urlencode(query)}")[0]
        features = json.loads(raw)["features"]
        return len(raw), features[0]["properties"]["GRAY_INDEX"] if features else None
    parts = pmap(one, p["grid"], 8)
    return out(200, sum(n for n, _ in parts), points=len(parts), categories=sorted({str(c) for _, c in parts}))


def soil_wcs(p):
    (x,), (y,) = warp("EPSG:4326", rasterio.CRS.from_string(IGH), [p["lon"]], [p["lat"]])

    def one(layer):
        name, depth = layer
        query = [("map", f"/map/{name}.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
                 ("COVERAGEID", f"{name}_{depth}_mean"), ("FORMAT", "image/tiff"), ("SUBSETTINGCRS", IGH_URI),
                 ("OUTPUTCRS", IGH_URI), ("SUBSET", f"X({x - 600},{x + 600})"), ("SUBSET", f"Y({y - 600},{y + 600})")]
        raw = http(f"{ISRIC_WCS}?{urlencode(query)}")[0]
        with MemoryFile(raw) as memory, memory.open() as ds:
            row, col = ds.index(x, y)
            return len(raw), int(ds.read(1)[row, col])
    parts = pmap(one, [(name, depth) for name in SOIL for depth in DEPTHS], 12)
    return out(200, sum(n for n, _ in parts), layers=len(parts), zero_layers=sum(v == 0 for _, v in parts))


def terrain_points(p):
    """Heights on a 5 m grid (coarser for big parcels) from the point-height service, 1000 points per request."""
    e0, n0, e1, n1 = p["box"]
    step = max(5, int(((e1 - e0) * (n1 - n0) / MAX_POINTS) ** 0.5) + 1)
    pts = [f"{n}%20{e}" for n in range(n0, n1 + 1, step) for e in range(e0, e1 + 1, step)]  # x = northing, y = easting
    call = lambda chunk: http(HEIGHT_API, ("request=GetHByPointList&list=" + ",".join(chunk)).encode())[0].decode()
    text = ",".join(pmap(call, [pts[i:i + 1000] for i in range(0, len(pts), 1000)], 8))
    rows = [r for r in (part.split() for part in text.split(",")) if len(r) == 3]
    if not rows:
        raise RuntimeError(f"asked for {len(pts)} points, no heights in the answer: {text[:300]}")
    return out(200, len(text), step_m=step, points=len(pts), zero_heights=sum(float(r[2]) == 0 for r in rows))


def satellite(p):
    """Planetary Computer: read token, one search per date window, classification of every scene, bands of 16."""
    t0, post = time.perf_counter(), {"Content-Type": "application/json"}
    token = json.loads(http(PC + "sas/v1/token/sentinel-2-l2a")[0])["token"]
    ends = [ANALYSIS_DATE] + [ANALYSIS_DATE.replace(year=ANALYSIS_DATE.year - k) + timedelta(days=15)
                              for k in range(1, YEARS_BACK + 1)]

    def search(end):
        body = {"collections": ["sentinel-2-l2a"], "limit": 100, "intersects": p["geom"],
                "datetime": f"{end - timedelta(days=30)}T00:00:00Z/{end}T23:59:59Z"}
        items, days = json.loads(http(PC + "stac/v1/search", json.dumps(body).encode(), post)[0])["features"], {}
        for item in items:  # one scene per acquisition day
            days.setdefault(item["properties"]["datetime"][:10], item)
        return [days[day] for day in sorted(days, reverse=True)]

    def read(task):
        with rasterio.Env(**GDAL), rasterio.open(f"{task[0]['assets'][task[1]]['href']}?{token}") as ds:
            data = rasterio.mask.mask(ds, [transform_geom("EPSG:4326", ds.crs, p["geom"])], crop=True, filled=False)[0]
        return int(data.count())
    windows, t1 = pmap(search, ends, len(ends)), time.perf_counter()
    scenes = [scene for window in windows for scene in window]
    classified, t2 = pmap(read, [(scene, "SCL") for scene in scenes], 16), time.perf_counter()
    chosen = windows[0][:SCENES_NOW] + [scene for window in windows[1:] for scene in window[:SCENES_PER_YEAR]]
    pixels = pmap(read, [(scene, band) for scene in chosen for band in BANDS], 16)
    return out(200, None, scl_reads=len(classified), band_reads=len(pixels), parcel_pixels_scl=classified[:1],
               search_s=round(t1 - t0, 3), scl_s=round(t2 - t1, 3), bands_s=round(time.perf_counter() - t2, 3))


def analysis(p):
    """One whole analysis through the running API: start it, follow every source until the analysis ends."""
    body, t0 = {"parcel_id": p["id"], "crop_id": CROP, "analysis_date": str(ANALYSIS_DATE)}, time.perf_counter()
    raw, _, _ = http(f"{API}/api/analyses", json.dumps(body).encode(), {"Content-Type": "application/json"})
    report_id, ended, state = json.loads(raw)["report_id"], {}, {"state": "running"}
    while state["state"] == "running" and time.perf_counter() - t0 < 90:
        time.sleep(0.25)
        state = json.loads(http(f"{API}/api/analyses/{report_id}/status")[0])
        for source in state["sources"]:
            if source["state"] in ("done", "missing") and source["id"] not in ended:
                ended[source["id"]] = {"state": source["state"], "after_s": round(time.perf_counter() - t0, 2),
                                       "note": source.get("note")}
    total, used = round(time.perf_counter() - t0, 2), None
    if state["state"] == "done":
        report = json.loads(http(f"{API}/api/reports/{report_id}")[0])
        used = [{k: s.get(k) for k in ("topic", "name", "mode", "chain_step", "missing")} for s in report["sources"]]
    return out(200, len(raw), state=state["state"], total_s=total, sources=ended, report_sources=used)


SOURCES = {"parcel:uldk": uldk, "weather:open-meteo": weather, "soil:iung-wms": soil_iung, "soil:isric-wcs": soil_wcs,
           "terrain:gugik-points": terrain_points, "satellite:planetary-computer": satellite}
OTHERS = list(SOURCES)[1:]


def probe_parcel(p, rep):
    base = {"parcel": p["id"], "repeat": rep}
    one = lambda name, mode: measure(name, "one source", {**base, "mode": mode}, lambda: SOURCES[name](p))
    if not one("parcel:uldk", "alone")["ok"] and "ring" not in p:
        return  # without the outline no other source can be asked
    for name in OTHERS:
        one(name, "alone")

    def together():  # as in an analysis: the parcel first, then every other source at the same time
        recs = [one("parcel:uldk", "together")] + pmap(lambda name: one(name, "together"), OTHERS, len(OTHERS))
        return out(None, None, failed=[r["source"] for r in recs if not r["ok"]])
    measure("all-sources", "parcel, then all other sources at the same time", base, together)


def main():
    print(f"performance probe {VERSION} on {HOST}; API: {API}; result file: {OUT_PATH}", flush=True)
    parcels = [{"id": pid, "lon": lon, "lat": lat} for pid, (lon, lat) in PARCELS.items()]
    try:
        for rep in range(1, REPEATS + 1):
            for p in parcels:
                probe_parcel(p, rep)
        if API:
            for group, size in [([p], 1) for p in parcels] + [(parcels[:AT_ONCE], AT_ONCE)]:
                pmap(lambda p: measure("api", "whole analysis", {"parcel": p["id"], "crop": CROP, "at_once": size},
                                       lambda: analysis(p)), group, size)
        RESULT["finished"] = True
    except KeyboardInterrupt:
        RESULT["interrupted"] = True
    finally:
        with LOCK:
            save()
        if os.geteuid() == 0:  # in Docker: hand the file to the owner of the directory
            os.chown(OUT_PATH, os.stat(".").st_uid, os.stat(".").st_gid)
        print(f"done in {RESULT['elapsed_s']} s; result file: {OUT_PATH}", flush=True)
        os._exit(0)  # do not wait for requests that are still hanging


if __name__ == "__main__":
    main()
