"""Sentinel-2 probe: times scene searches and parallel COG window reads on two free hosts.

Run it with the Docker command from scripts/probes/README.md. It writes one file,
satellite-probe-<host>-<UTC time>.json, to the current directory.
Only parcel outlines and dates are sent to external services.
"""
import concurrent.futures as cf
import json
import os
import socket
import sys
import time
import traceback
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import rasterio
import rasterio.mask
from rasterio.warp import transform_geom

VERSION = "1.0.0"
ANALYSIS_DATE = date(2023, 6, 20)
WINDOW_DAYS, YEARS_PARALLEL, BATCH_SIZES = (30, 90, 365, 3650), (4, 10), (1, 4, 8, 16)
BANDS, REPEATS = ("scl", "red", "nir", "nir08", "swir16"), 3
SEARCH_TIMEOUT_S, BATCH_TIMEOUT_S, THREADS, THREADS_VARIANT = 30, 30, 16, 32
GDAL_OPTIONS = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_TIMEOUT": 20,
                "GDAL_HTTP_CONNECTTIMEOUT": 10}
# Two free hosts of the same Sentinel-2 L2A archive; asset names differ.
ES_OTHER = ("aot", "blue", "coastal", "green", "nir09", "rededge1", "rededge2", "rededge3", "swir22",
            "visual", "wvp", "granule_metadata", "tileinfo_metadata", "thumbnail")
ES_DETAILS = ("proj:shape", "proj:transform", "roles", "eo:bands", "title", "type", "gsd", "raster:bands")
SOURCES = {
    "earth-search": {
        "search_url": "https://earth-search.aws.element84.com/v1/search", "limit": 2000,
        "token_url": None, "assets": dict(zip(BANDS, BANDS)),
        # Earth Search returns every asset unless the unwanted ones are excluded by name.
        "exclude": [f"assets.{a}" for a in ES_OTHER] + [f"assets.{a}-jp2" for a in ES_OTHER + BANDS]
        + [f"assets.{b}.{d}" for b in BANDS for d in ES_DETAILS]},
    "planetary-computer": {
        "search_url": "https://planetarycomputer.microsoft.com/api/stac/v1/search", "limit": 1000,
        "token_url": "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a",
        "assets": dict(zip(BANDS, ("SCL", "B04", "B08", "B8A", "B11"))), "exclude": []},
}
COLLECTION = "sentinel-2-l2a"
PROPERTIES = ("datetime", "eo:cloud_cover", "s2:processing_baseline", "grid:code", "s2:mgrs_tile",
              "earthsearch:boa_offset_applied")
# Test parcels (cadastral id -> region, simplified outline as lon/lat ring).
PARCELS = {
    "040704_2.0020.34/2": ("kujawsko-pomorskie, 2.5 ha", [
        [18.202447, 52.749197], [18.200317, 52.750263], [18.199112, 52.749417], [18.201061, 52.748485],
        [18.201620, 52.748218], [18.202447, 52.749197]]),
    "022003_5.0007.170/4": ("dolnoslaskie, 5 ha", [
        [17.048244, 51.349763], [17.049458, 51.349477], [17.050788, 51.349393], [17.051103, 51.351404],
        [17.047432, 51.351590], [17.047540, 51.351149], [17.048244, 51.349763]]),
    "120805_5.0007.41": ("malopolskie, 1.3 ha, 40 m wide strip", [
        [19.949403, 50.348508], [19.950044, 50.348444], [19.950161, 50.349324], [19.950431, 50.350752],
        [19.950609, 50.351692], [19.949963, 50.351734], [19.949564, 50.349414], [19.949403, 50.348508]]),
}

HOST = os.environ.get("PROBE_HOST") or socket.gethostname()
STARTED = datetime.now(timezone.utc)
OUT_PATH = f"satellite-probe-{HOST}-{STARTED:%Y%m%dT%H%M%SZ}.json"
RESULT = {"probe": "satellite", "version": VERSION, "started_utc": STARTED.isoformat(), "host": HOST,
          "python": sys.version.split()[0], "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
          "analysis_date": str(ANALYSIS_DATE), "gdal_options": GDAL_OPTIONS, "finished": False, "queries": []}


def save():
    RESULT["elapsed_s"] = round((datetime.now(timezone.utc) - STARTED).total_seconds(), 1)
    with open(OUT_PATH + ".tmp", "w") as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=1)
    os.replace(OUT_PATH + ".tmp", OUT_PATH)


def measure(source, description, params, fn):
    """Run one query, record timing and outcome, never raise (except on Ctrl-C)."""
    rec = {"source": source, "description": description, "params": params}
    t0, value = time.perf_counter(), None
    try:
        value, info = fn()
        rec.update(ok=True, **info)
    except Exception as exc:
        rec.update(ok=False, http_status=getattr(exc, "code", None), error=traceback.format_exc())
    rec["seconds"] = round(time.perf_counter() - t0, 3)
    RESULT["queries"].append(rec)
    save()
    print(f"[{len(RESULT['queries']):3d}] {rec['seconds']:7.2f} s  {'ok ' if rec['ok'] else 'ERR'} "
          f"{source}: {description} {json.dumps(params)}", flush=True)
    return value


def http_json(url, body=None):
    """GET (or POST when a body is given) and decode JSON. Returns (data, status, size)."""
    headers = {"Content-Type": "application/json", "User-Agent": f"satellite-probe/{VERSION}"}
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None, headers)
    with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT_S) as resp:
        raw = resp.read()
        return json.loads(raw), resp.status, len(raw)


def tile_of(item):
    return item["properties"].get("grid:code") or item["properties"].get("s2:mgrs_tile")


def search(name, ring, start, end):
    """One STAC search with paging, asking only for the fields needed. Returns (items, info)."""
    src = SOURCES[name]
    body = {"collections": [COLLECTION], "limit": src["limit"],
            "intersects": {"type": "Polygon", "coordinates": [ring]},
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "fields": {"include": ["id"] + [f"properties.{p}" for p in PROPERTIES]
                       + [f"assets.{a}.href" for a in src["assets"].values()],
                       "exclude": ["links", "geometry", "bbox", "stac_extensions"] + src["exclude"]}}
    url, items, size, pages, status = src["search_url"], [], 0, 0, None
    while url:
        page, status, nbytes = http_json(url, body)
        size, pages = size + nbytes, pages + 1
        items += page["features"]
        nxt = [ln for ln in page.get("links", []) if ln.get("rel") == "next"]
        if not nxt or len(page["features"]) < src["limit"]:
            break
        url = nxt[0]["href"]
        body = {**body, **nxt[0]["body"]} if nxt[0].get("merge") else nxt[0].get("body", body)
    days = sorted({it["properties"]["datetime"][:10] for it in items})
    baselines = Counter(str(it["properties"].get("s2:processing_baseline")) for it in items)
    return items, {"http_status": status, "bytes": size, "summary": {
        "items": len(items), "pages": pages, "acquisition_days": len(days), "first_last_day": days[:1] + days[-1:],
        "tiles": dict(Counter(map(tile_of, items))), "baselines": dict(baselines)}}


def search_years(name, ring, years):
    """One 30-day search per year, all in parallel. Returns (items, info)."""
    def one(year_back):
        end = ANALYSIS_DATE.replace(year=ANALYSIS_DATE.year - year_back)
        return search(name, ring, end - timedelta(days=30), end)
    with cf.ThreadPoolExecutor(max_workers=years) as pool:
        parts = list(pool.map(one, range(years)))
    return [it for items, _ in parts for it in items], {
        "http_status": 200, "bytes": sum(info["bytes"] for _, info in parts),
        "summary": {"items_per_year": [len(items) for items, _ in parts]}}


def one_per_day(items):
    """Drop duplicates: keep one tile and the newest processing for each acquisition day."""
    tile = Counter(tile_of(it) for it in items).most_common(1)[0][0]
    best = {}
    for it in items:
        key = (it["properties"].get("s2:processing_baseline") or "", it["id"])
        day = it["properties"]["datetime"][:10]
        if tile_of(it) == tile and (day not in best or key > best[day][0]):
            best[day] = (key, it)
    return [best[day][1] for day in sorted(best, reverse=True)]


def read_band(item, href, band, geom):
    """Read the pixels of one band whose centres fall inside the parcel."""
    t0 = time.perf_counter()
    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(href) as ds:
        shape = transform_geom("EPSG:4326", ds.crs, geom)
        data, _ = rasterio.mask.mask(ds, [shape], crop=True, filled=False)
        file_offset, block = ds.offsets[0], ds.block_shapes[0]
    pixels = data.compressed()
    props = item["properties"]
    out = {"id": item["id"], "band": band, "ok": True, "seconds": round(time.perf_counter() - t0, 3),
           "window": list(data.shape[1:]), "pixels": int(pixels.size), "bytes": int(data.nbytes),
           "block": list(block), "file_offset": file_offset, "baseline": props.get("s2:processing_baseline"),
           "boa_offset_applied": props.get("earthsearch:boa_offset_applied")}
    if band == "scl":
        out["classes"] = {str(k): v for k, v in Counter(pixels.tolist()).items()}
    elif pixels.size:
        out["mean_dn"] = round(float(pixels.mean()), 1)
    return out


def fetch_token(url):
    data, status, size = http_json(url)
    return data["token"], {"http_status": status, "bytes": size, "summary": data.get("msft:expiry")}


def read_batch(name, token, scenes, n, bands, geom, threads):
    """Read all (scene, band) files with a pool of threads. Returns (files, info)."""
    if len(scenes) < n or (SOURCES[name]["token_url"] and not token):
        raise RuntimeError("not enough scenes from the search, or no read token")
    tasks = [(scene, band) for scene in scenes for band in bands]
    href = lambda s, b: s["assets"][SOURCES[name]["assets"][b]]["href"] + (f"?{token}" if token else "")
    pool = cf.ThreadPoolExecutor(max_workers=threads)
    futures = {pool.submit(lambda s=s, b=b: read_band(s, href(s, b), b, geom)): (s["id"], b) for s, b in tasks}
    _, pending = cf.wait(futures, timeout=BATCH_TIMEOUT_S)
    pool.shutdown(wait=False, cancel_futures=True)
    files = []
    for fut, (scene_id, band) in futures.items():
        if fut in pending:
            files.append({"id": scene_id, "band": band, "ok": False, "error": "batch timeout"})
        elif fut.exception():
            error = "".join(traceback.format_exception(fut.exception()))
            files.append({"id": scene_id, "band": band, "ok": False, "error": error})
        else:
            files.append(fut.result())
    failed = sum(not f["ok"] for f in files)
    if failed == len(files):
        raise RuntimeError("all reads failed: " + files[0]["error"])
    return files, {"http_status": None, "bytes": sum(f.get("bytes", 0) for f in files), "summary": {
        "files": len(files), "failed": failed, "slowest_file_s": max(f.get("seconds", 0) for f in files)},
        "files": files}


def probe_source(name, parcel_id, region, ring):
    src, geom = SOURCES[name], {"type": "Polygon", "coordinates": [ring]}
    base, pool, token = {"parcel": parcel_id, "region": region}, [], None
    for rep in range(1, REPEATS + 1):
        if src["token_url"]:
            token = measure(name, "read token request", {**base, "repeat": rep},
                            lambda: fetch_token(src["token_url"])) or token
        for days in WINDOW_DAYS:
            items = measure(name, f"search, {days}-day window", {**base, "window_days": days, "repeat": rep},
                            lambda: search(name, ring, ANALYSIS_DATE - timedelta(days=days), ANALYSIS_DATE))
            if days == max(WINDOW_DAYS) and items:
                pool = one_per_day(items)
        for years in YEARS_PARALLEL:
            measure(name, "parallel searches, one 30-day window per year",
                    {**base, "years": years, "repeat": rep}, lambda: search_years(name, ring, years))
    # Every batch reads scenes not read before, so no timing benefits from a warm cache.
    plan = [(bands, n, THREADS) for bands in (("scl",), BANDS) for n in BATCH_SIZES]
    for bands, n, threads in plan + [(BANDS, max(BATCH_SIZES), THREADS_VARIANT)]:
        for rep in range(1, REPEATS + 1):
            scenes, pool = pool[:n], pool[n:]
            measure(name, f"parallel read, {n} scene(s), {len(bands)} band(s) each, {threads} threads",
                    {**base, "scenes": n, "bands": list(bands), "threads": threads, "repeat": rep},
                    lambda: read_batch(name, token, scenes, n, bands, geom, threads))


def main():
    print(f"satellite probe {VERSION} on {HOST}; result file: {OUT_PATH}", flush=True)
    try:
        for parcel_id, (region, ring) in PARCELS.items():
            for name in SOURCES:
                probe_source(name, parcel_id, region, ring)
        RESULT["finished"] = True
    except KeyboardInterrupt:
        RESULT["interrupted"] = True
    finally:
        save()
        if os.geteuid() == 0:  # in Docker: hand the file to the owner of the directory
            os.chown(OUT_PATH, os.stat(".").st_uid, os.stat(".").st_gid)
        print(f"done in {RESULT['elapsed_s']} s; result file: {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
