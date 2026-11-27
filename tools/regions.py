#!/usr/bin/env python3
"""FluxoNav's regional maps: a country's OpenStreetMap extract cut by its own regions (boundary=administrative at the
country's level from countries.json), each written as a Mapsforge map by the workflow (.github/workflows/regions.yml).

  python3 tools/regions.py split BOUNDARIES.geojson COUNTRY OUT
      the regions (osmium export of the country's administrative boundaries) → OUT/<id>.geojson, OUT/extract.json
      (osmium extract's config) and OUT/regions.json (id, names, box)
  python3 tools/regions.py land OUT LAND.shp
      land and sea for each region (osmdata.openstreetmap.de's land polygons): OUT/<id>-land.osm — the land as
      natural=nosea, a sea rectangle around it as natural=sea (as the Mapsforge maps are made)
  python3 tools/regions.py catalog OUT MAPS TAG REPO OLD_CATALOG NEW_CATALOG
      the maps written → their sizes, sha256 and addresses in the catalogue of all countries (catalog.json)
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import unicodedata

LANGS = ("en", "ru", "de", "fr", "es", "uk", "fi", "sv", "et", "lv", "lt", "pl", "no", "nb", "da")
BIG_ID = 100_000_000_000_000   # land and sea: ids far above OpenStreetMap's own


def slug(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    out = "".join(c if c.isalnum() else "-" for c in t)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "region"


def rings_of(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def box(geom):
    xs, ys = [], []
    for poly in rings_of(geom):
        for p in poly[0]:
            xs.append(p[0])
            ys.append(p[1])
    return [min(ys), min(xs), max(ys), max(xs)]   # south, west, north, east


def simplify(pts, tol):
    """Douglas–Peucker on a ring of [lon, lat] points."""
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a][0], pts[a][1]
        bx, by = pts[b][0], pts[b][1]
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i][0], pts[i][1]
            d = abs(dy * (px - ax) - dx * (py - ay)) / length if length > 0 else ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [q for q, k in zip(pts, keep) if k]


def outline(geom, tol=0.003, min_area=0.0004):
    """The region's shape for the app (which map holds a place — the boxes of neighbours overlap): its outer rings
    without the tiny islands, simplified to ~300 m, as flat [lon, lat, lon, lat…] lists."""
    out = []
    for poly in rings_of(geom):
        ring = poly[0]
        xs = [q[0] for q in ring]
        ys = [q[1] for q in ring]
        if (max(xs) - min(xs)) * (max(ys) - min(ys)) < min_area:
            continue
        s = simplify(ring, tol)
        if len(s) >= 4:
            out.append([round(v, 4) for q in s for v in q[:2]])
    return out


def split(boundaries, country, out):
    conf = json.load(open("countries.json", encoding="utf-8"))[country]
    level = str(conf["level"])
    iso = conf["iso"]
    feats = json.load(open(boundaries, encoding="utf-8"))["features"]
    os.makedirs(out, exist_ok=True)
    # What the boundaries hold (to see why a level has nothing): the areas by their level, a few names of each.
    levels = {}
    for f in feats:
        p = f.get("properties") or {}
        key = (p.get("boundary"), str(p.get("admin_level")), (f.get("geometry") or {}).get("type"))
        levels.setdefault(key, []).append(p.get("name"))
    print("%d areas in the boundaries:" % len(feats))
    for key in sorted(levels, key=str):
        print("  %-60s %4d  %s" % (key, len(levels[key]), ", ".join(str(n) for n in levels[key][:5])))
    if feats:
        print("  properties of the first:", sorted((feats[0].get("properties") or {}).keys())[:30])
    regions, extracts, seen = [], [], set()
    for f in feats:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        if p.get("boundary") != "administrative" or str(p.get("admin_level")) != level or not p.get("name"):
            continue
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        rid = iso.lower() + "-" + slug(p.get("name:en") or p["name"])
        if rid in seen:
            rid += "-" + slug(str(p.get("@id") or len(seen)))
        seen.add(rid)
        names = {"default": p["name"]}
        for lang in LANGS:
            v = p.get("name:" + lang)
            if v:
                names[lang] = v
        poly = os.path.abspath(os.path.join(out, rid + ".geojson"))
        with open(poly, "w", encoding="utf-8") as w:
            json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": p["name"]},
                                                                   "geometry": g}]}, w)
        extracts.append({"output": rid + ".osm.pbf", "polygon": {"file_name": poly, "file_type": "geojson"}})
        # A region with a country code of its own (the Åland Islands: AX) — the app finds its maps by the country.
        own_iso = next((v for k, v in conf.get("iso_by_region", {}).items() if rid.startswith(k)), iso)
        regions.append({"id": rid, "iso": own_iso, "names": names,
                        "box": [round(v, 5) for v in box(g)], "shape": outline(g)})
    regions.sort(key=lambda r: r["id"])
    with open(os.path.join(out, "extract.json"), "w", encoding="utf-8") as w:
        json.dump({"directory": os.path.abspath(out), "extracts": extracts}, w, indent=1)
    with open(os.path.join(out, "regions.json"), "w", encoding="utf-8") as w:
        json.dump(regions, w, ensure_ascii=False, indent=1)
    print("%d regions of %s (admin_level %s):" % (len(regions), country, level))
    for r in regions:
        print("  %-36s %s" % (r["id"], r["names"].get("ru") or r["names"]["default"]))
    if not regions:
        sys.exit("no regions found")


class Osm:
    """A small OSM XML writer: nodes first, then ways, then relations (osmium merge wants them sorted)."""

    def __init__(self):
        self.nodes, self.ways, self.rels = [], [], []
        self.nid = BIG_ID
        self.wid = BIG_ID
        self.rid = BIG_ID

    def ring(self, coords, tags=None):
        pts = [c[:2] for c in coords]
        if len(pts) < 4:
            return None
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        ids = []
        for lon, lat in pts[:-1]:
            self.nid += 1
            self.nodes.append((self.nid, lat, lon))
            ids.append(self.nid)
        ids.append(ids[0])
        self.wid += 1
        self.ways.append((self.wid, ids, tags or {}))
        return self.wid

    def area(self, rings, tags):
        if len(rings) == 1:
            self.ring(rings[0], tags)
            return
        outer = self.ring(rings[0])
        inner = [self.ring(r) for r in rings[1:]]
        if outer is None:
            return
        self.rid += 1
        members = [("outer", outer)] + [("inner", i) for i in inner if i is not None]
        self.rels.append((self.rid, members, dict(tags, type="multipolygon")))

    def write(self, path):
        stamp = ' version="1" timestamp="2026-01-01T00:00:00Z"'
        with open(path, "w", encoding="utf-8") as w:
            w.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="fluxonav-maps">\n')
            for i, lat, lon in self.nodes:
                w.write('<node id="%d"%s lat="%.7f" lon="%.7f"/>\n' % (i, stamp, lat, lon))
            for i, refs, tags in self.ways:
                w.write('<way id="%d"%s>' % (i, stamp) + "".join('<nd ref="%d"/>' % r for r in refs) +
                        "".join('<tag k="%s" v="%s"/>' % kv for kv in tags.items()) + "</way>\n")
            for i, members, tags in self.rels:
                w.write('<relation id="%d"%s>' % (i, stamp) +
                        "".join('<member type="way" ref="%d" role="%s"/>' % (ref, role) for role, ref in members) +
                        "".join('<tag k="%s" v="%s"/>' % kv for kv in tags.items()) + "</relation>\n")
            w.write("</osm>\n")


def land(out, shp):
    regions = json.load(open(os.path.join(out, "regions.json"), encoding="utf-8"))
    for r in regions:
        s, w, n, e = r["box"]
        s, w, n, e = s - 0.05, w - 0.05, n + 0.05, e + 0.05
        clip = os.path.join(out, r["id"] + "-land.geojson")
        if os.path.exists(clip):
            os.remove(clip)
        subprocess.run(["ogr2ogr", "-f", "GeoJSON", "-spat", str(w), str(s), str(e), str(n),
                        "-clipsrc", str(w), str(s), str(e), str(n), clip, shp], check=True)
        osm = Osm()
        # The sea first: one rectangle around the region; the land drawn over it.
        osm.ring([[w - 0.05, s - 0.05], [e + 0.05, s - 0.05], [e + 0.05, n + 0.05], [w - 0.05, n + 0.05], [w - 0.05, s - 0.05]],
                 {"natural": "sea", "layer": "-5"})
        count = 0
        for f in json.load(open(clip, encoding="utf-8")).get("features", []):
            for rings in rings_of(f.get("geometry") or {}):
                osm.area(rings, {"natural": "nosea", "layer": "-5"})
                count += 1
        osm.write(os.path.join(out, r["id"] + "-land.osm"))
        os.remove(clip)
        print("  %-36s land polygons: %d" % (r["id"], count))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def catalog(out, maps, tag, repo, old_path, new_path):
    regions = json.load(open(os.path.join(out, "regions.json"), encoding="utf-8"))
    country = tag.split("-")[0]
    items = []
    for r in regions:
        f = os.path.join(maps, r["id"] + ".map")
        if not os.path.isfile(f):
            print("missing:", f)
            continue
        items.append({"id": r["id"], "iso": r["iso"], "names": r["names"], "box": r["box"], "shape": r.get("shape", []),
                      "file": r["id"] + ".map", "size": os.path.getsize(f), "sha256": sha256(f),
                      "url": "https://github.com/%s/releases/download/%s/%s.map" % (repo, tag, r["id"])})
    try:
        cat = json.load(open(old_path, encoding="utf-8"))
    except Exception:
        cat = {"version": 1, "countries": {}}
    cat["updated"] = datetime.date.today().isoformat()
    cat.setdefault("countries", {})[country] = {"tag": tag, "date": datetime.date.today().isoformat(), "maps": items}
    with open(new_path, "w", encoding="utf-8") as w:
        json.dump(cat, w, ensure_ascii=False, indent=1)
    print("%s: %d maps, %.1f MB" % (country, len(items), sum(i["size"] for i in items) / 1e6))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "split":
        split(*args)
    elif cmd == "land":
        land(*args)
    elif cmd == "catalog":
        catalog(*args)
    else:
        sys.exit(__doc__)
