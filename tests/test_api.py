
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == (
        "Geospatial File Measurement API is running"
    )


def test_upload_kml_and_measurements():
    kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <name>Test Point</name>
          <Point>
            <coordinates>78.4867,17.385,0</coordinates>
          </Point>
        </Placemark>
        <Placemark>
          <name>Test Line</name>
          <LineString>
            <coordinates>
              78.4867,17.385,0 78.4967,17.395,0
            </coordinates>
          </LineString>
        </Placemark>
        <Placemark>
          <name>Test Polygon</name>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  78.48,17.38,0 78.49,17.38,0
                  78.49,17.39,0 78.48,17.39,0
                  78.48,17.38,0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """

    response = client.post(
        "/api/files/",
        files={
            "file": (
                "test.kml",
                kml_content,
                "application/vnd.google-earth.kml+xml",
            )
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["feature_count"] == 3

    file_id = data["id"]
    measurements_response = client.get(
        f"/api/files/{file_id}/measurements/"
    )

    assert measurements_response.status_code == 200
    measurements = measurements_response.json()["measurements"]
    assert len(measurements) == 3

    assert measurements[0]["geometry_type"] == "Point"
    assert measurements[1]["geometry_type"] == "LineString"
    assert measurements[1]["length_m"] > 0
    assert measurements[2]["geometry_type"] == "Polygon"
    assert measurements[2]["area_m2"] > 0


def test_missing_file_returns_404():
    response = client.get(
        "/api/files/does-not-exist/measurements/"
    )
    assert response.status_code == 404
