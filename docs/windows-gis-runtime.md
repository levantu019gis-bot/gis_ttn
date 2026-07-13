# Windows GIS Runtime Troubleshooting

The app initializes `PROJ_DATA`, `PROJ_LIB`, and `GDAL_DATA` before importing
`rasterio`, GDAL, or `pyproj`. This prevents Windows machines with another GIS
stack installed from accidentally loading an incompatible `proj.db`.

## Common Symptom

If PostgreSQL/PostGIS is installed, failures may mention a PROJ database similar
to:

```text
C:\Program Files\PostgreSQL\...\postgis-...\proj\proj.db
```

That path should not be used by this app. The expected source/development paths
are under the active Conda environment:

```text
...\ttn-env\Library\share\proj
...\ttn-env\Library\share\gdal
```

## Smoke Check From Source

Run from the repository root:

```powershell
$env:PYTHONPATH="src"
python -c "from thucthengay.runtime import gis_runtime_diagnostics; print(gis_runtime_diagnostics())"
python -m thucthengay.app --smoke
```

Expected diagnostics include:

```text
proj_db_valid: True
PROJ_DATA: ...\ttn-env\Library\share\proj
GDAL_DATA: ...\ttn-env\Library\share\gdal
```

## Packaged Builds

The PyInstaller runtime hook applies the same rule inside the packaged runtime.
If a packaged executable fails with PROJ/GDAL errors, rebuild from the Conda
environment and verify the bundled `Library\share\proj` and `Library\share\gdal`
folders exist next to the executable runtime.
