# FluxoNav maps

Free offline maps for the FluxoNav navigator (Android phone and Wear OS watch): countries cut into their regions,
made from OpenStreetMap data, in the Mapsforge format.

Бесплатные офлайн-карты для навигатора FluxoNav (телефон и часы): страны по регионам, из данных OpenStreetMap,
в формате Mapsforge.

## Licences / Лицензии

- **Map data © OpenStreetMap contributors** — https://www.openstreetmap.org/copyright. The map files are made available
  under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
- Land and sea: land polygons from [osmdata.openstreetmap.de](https://osmdata.openstreetmap.de/) (© OpenStreetMap
  contributors, ODbL).
- Country extracts: [Geofabrik](https://download.geofabrik.de/) (© OpenStreetMap contributors, ODbL).
- The scripts of this repository: MIT licence ([LICENSE](LICENSE)).

## How the maps are made

[`.github/workflows/regions.yml`](.github/workflows/regions.yml), run by hand for a country of
[`countries.json`](countries.json):

1. the country's OpenStreetMap extract from Geofabrik;
2. its regions — OpenStreetMap's own administrative boundaries at the country's level
   ([`tools/regions.py`](tools/regions.py) `split`);
3. each region cut out with osmium; land and sea added from osmdata.openstreetmap.de (`land`);
4. each written as a Mapsforge map (osmosis + mapsforge-map-writer 0.25.0, the standard tag mapping, label positions);
5. published as a release `<country>-<date>`; `catalog.json` in the release `catalog` lists the latest maps of every
   country (names, boxes, sizes, sha256, addresses).
