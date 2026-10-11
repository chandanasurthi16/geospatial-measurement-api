# Geospatial File Measurement API

A Python-based REST API for uploading geospatial files, extracting geographic features, and calculating area and length measurements.

## Features

- Upload KML files and zipped Shapefiles.
- Extract feature geometries, coordinates, and properties.
- Calculate polygon area in square meters.
- Calculate line length in meters.
- Transform geometries into a suitable projected coordinate reference system for measurement.
- Retrieve uploaded file metadata, features, and measurements.
- Interactive API documentation using Swagger UI.
- Automated tests using pytest.

## Technology Stack

- **Python**
- **FastAPI** — REST API framework
- **GeoPandas** — geospatial data processing
- **Shapely** — geometry operations
- **PyProj** — coordinate transformations
- **Uvicorn** — ASGI server
- **Pytest** — automated testing

## Requirements

- Python 3.10 or newer
- pip

## Installation

Clone the repository:

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd geospatial-measurement-api
```

Create and activate a virtual environment.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn main:app --reload
```

Open the interactive documentation:

http://127.0.0.1:8000/docs

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Check API status |
| POST | `/api/files/` | Upload a KML or zipped Shapefile |
| GET | `/api/files/{file_id}/` | Retrieve file metadata |
| GET | `/api/files/{file_id}/features/` | Retrieve extracted features |
| GET | `/api/files/{file_id}/measurements/` | Retrieve area and length measurements |

## Example Measurement Response

```json
{
  "geometry_type": "Polygon",
  "area_m2": 1177219.37,
  "length_m": null
}
```

Point geometries have no area or length measurement. Line geometries return length in meters, while polygon geometries return area in square meters.

## Run Tests

```bash
python -m pytest -v
```

## Current Limitations

- Uploaded file metadata and features are stored in memory and are cleared when the server restarts.
- Shapefiles must be uploaded as ZIP archives containing the required Shapefile components.
- The API currently limits uploads to 25 MB.

## Project Status

Core upload, feature extraction, measurement, and retrieval endpoints have been tested successfully. Automated tests cover the health endpoint, KML upload and measurements, and missing-file handling.