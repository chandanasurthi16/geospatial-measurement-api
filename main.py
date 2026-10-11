
import json
import math
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

import geopandas as gpd
from fastapi import FastAPI, File, HTTPException, UploadFile
from pyproj import CRS, Transformer
from shapely.geometry import (
    Point,
    LineString,
    Polygon,
    MultiPoint,
    MultiLineString,
    MultiPolygon,
    GeometryCollection,
    mapping,
)
from shapely.ops import transform

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload KML or zipped Shapefiles and measure geographic features.",
    version="1.0.0",
)

# In-memory storage for this MVP. Records reset when the server restarts.
file_records = {}


def parse_coordinates(text):
    """Parse KML coordinates into (longitude, latitude) tuples."""
    if not text or not text.strip():
        return []
    result = []
    for item in text.strip().split():
        values = item.split(",")
        if len(values) >= 2:
            result.append((float(values[0]), float(values[1])))
    return result


def parse_kml_geometry(element):
    """Convert supported KML geometry elements to Shapely geometries."""
    tag = element.tag.split("}")[-1]

    if tag == "Point":
        node = element.find(".//{*}coordinates")
        coords = parse_coordinates(node.text if node is not None else "")
        return Point(coords[0]) if coords else None

    if tag == "LineString":
        node = element.find(".//{*}coordinates")
        coords = parse_coordinates(node.text if node is not None else "")
        return LineString(coords) if len(coords) >= 2 else None

    if tag == "Polygon":
        rings = []
        for node in element.findall(
            ".//{*}outerBoundaryIs/{*}LinearRing/{*}coordinates"
        ):
            rings.append(parse_coordinates(node.text or ""))
        holes = []
        for node in element.findall(
            ".//{*}innerBoundaryIs/{*}LinearRing/{*}coordinates"
        ):
            holes.append(parse_coordinates(node.text or ""))
        if not rings or len(rings[0]) < 4:
            return None
        return Polygon(rings[0], holes)

    if tag == "MultiGeometry":
        geometries = [
            parse_kml_geometry(child)
            for child in element
            if child.tag.split("}")[-1]
            in ("Point", "LineString", "Polygon", "MultiGeometry")
        ]
        geometries = [g for g in geometries if g is not None]
        return GeometryCollection(geometries) if geometries else None

    return None


def read_kml(content):
    """Read KML placemarks and return features in EPSG:4326."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("Invalid KML/XML file.") from exc

    features = []
    for placemark in root.findall(".//{*}Placemark"):
        geometry = None
        properties = {}

        for child in placemark:
            tag = child.tag.split("}")[-1]
            if tag in ("Point", "LineString", "Polygon", "MultiGeometry"):
                geometry = parse_kml_geometry(child)
            elif tag in ("name", "description"):
                properties[tag] = child.text or ""
            elif tag == "ExtendedData":
                for data in child.findall(".//{*}Data"):
                    key = data.attrib.get("name", "value")
                    value = data.find("{*}value")
                    properties[key] = value.text if value is not None else None
                for data in child.findall(".//{*}SimpleData"):
                    properties[data.attrib.get("name", "value")] = data.text

        if geometry is not None and not geometry.is_empty:
            features.append({"geometry": geometry, "properties": properties})

    if not features:
        raise ValueError("No supported Placemark geometries found in KML.")

    return gpd.GeoDataFrame(
        features, geometry="geometry", crs="EPSG:4326"
    )


def read_shapefile_zip(content):
    """Safely extract a zipped Shapefile and load its geometry data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir).resolve()

        with zipfile.ZipFile(__import__("io").BytesIO(content)) as archive:
            for member in archive.infolist():
                destination = (root / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    raise ValueError("ZIP contains an unsafe file path.")
            archive.extractall(root)

        shp_files = list(root.rglob("*.shp"))
        if len(shp_files) != 1:
            raise ValueError(
                "ZIP must contain exactly one .shp file and its companion files."
            )

        gdf = gpd.read_file(shp_files[0])

        if gdf.empty:
            raise ValueError("The Shapefile contains no features.")
        if gdf.crs is None:
            raise ValueError(
                "Shapefile CRS is missing. Include its .prj file."
            )

        return gdf


def calculate_measurement(geometry, source_crs):
    """Measure polygons and lines in a local UTM CRS, using metres."""
    if geometry is None or geometry.is_empty:
        return {"area_m2": None, "length_m": None}

    if geometry.geom_type not in (
        "Polygon", "MultiPolygon", "LineString", "MultiLineString"
    ):
        return {"area_m2": None, "length_m": None}

    source = CRS.from_user_input(source_crs)
    wgs84 = CRS.from_epsg(4326)

    to_wgs84 = Transformer.from_crs(
        source, wgs84, always_xy=True
    ).transform
    geographic_geometry = transform(to_wgs84, geometry)

    point = geographic_geometry.representative_point()
    lon, lat = point.x, point.y

    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Geometry coordinates are outside valid bounds.")

    zone = max(1, min(60, math.floor((lon + 180) / 6) + 1))
    epsg = (32600 if lat >= 0 else 32700) + zone
    projected_crs = CRS.from_epsg(epsg)

    project = Transformer.from_crs(
        source, projected_crs, always_xy=True
    ).transform
    projected_geometry = transform(project, geometry)

    area = (
        projected_geometry.area
        if geometry.geom_type in ("Polygon", "MultiPolygon")
        else None
    )
    length = (
        projected_geometry.length
        if geometry.geom_type in ("LineString", "MultiLineString")
        else None
    )

    return {
        "area_m2": round(area, 3) if area is not None else None,
        "length_m": round(length, 3) if length is not None else None,
    }


@app.get("/")
def home():
    return {"message": "Geospatial File Measurement API is running"}


@app.post("/api/files/", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()

    if extension not in (".kml", ".zip"):
        raise HTTPException(
            status_code=400,
            detail="Only .kml and .zip (Shapefile) files are supported.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    try:
        if extension == ".kml":
            gdf = read_kml(content)
        else:
            if not zipfile.is_zipfile(__import__("io").BytesIO(content)):
                raise ValueError("Uploaded ZIP file is invalid.")
            gdf = read_shapefile_zip(content)

        if gdf.crs is None:
            raise ValueError("Source CRS is missing.")

        source_crs = CRS.from_user_input(gdf.crs)
        features = []

        for index, row in gdf.iterrows():
            geometry = row.geometry
            properties = {
                key: (value.item() if hasattr(value, "item") else value)
                for key, value in row.drop(labels=["geometry"]).to_dict().items()
            }

            measurement = calculate_measurement(geometry, source_crs)
            features.append({
                "feature_id": int(index) if isinstance(index, int) else str(index),
                "geometry_type": geometry.geom_type if geometry is not None else None,
                "geometry": mapping(geometry) if geometry is not None else None,
                "crs": source_crs.to_string(),
                "properties": properties,
                "measurements": measurement,
            })

        record_id = str(uuid4())
        file_records[record_id] = {
            "id": record_id,
            "filename": filename,
            "feature_count": len(features),
            "crs": source_crs.to_string(),
            "status": "COMPLETED",
            "features": features,
        }

        return {
            key: value
            for key, value in file_records[record_id].items()
            if key != "features"
        }

    except HTTPException:
        raise
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not process geospatial file: {exc}",
        ) from exc


@app.get("/api/files/{file_id}/")
def get_file_info(file_id: str):
    record = file_records.get(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File ID not found.")

    return {key: value for key, value in record.items() if key != "features"}


@app.get("/api/files/{file_id}/measurements/")
def get_measurements(file_id: str):
    record = file_records.get(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File ID not found.")

    return {
        "id": file_id,
        "filename": record["filename"],
        "feature_count": record["feature_count"],
        "crs": record["crs"],
        "measurements": [
            {
                "feature_id": feature["feature_id"],
                "geometry_type": feature["geometry_type"],
                **feature["measurements"],
            }
            for feature in record["features"]
        ],
    }


@app.get("/api/files/{file_id}/features/")
def get_features(file_id: str):
    record = file_records.get(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File ID not found.")
    return {"id": file_id, "features": record["features"]}
