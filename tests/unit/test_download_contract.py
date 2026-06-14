from __future__ import annotations

from pathlib import Path

import pytest

from thucthengay.download import (
    DownloadFilenameFormatRule,
    SatelliteDownloadConfigError,
    SatelliteDownloadRequest,
    resolve_download_request,
)


def test_resolve_download_request_accepts_relative_and_absolute_paths(tmp_path: Path) -> None:
    base = tmp_path / "project"
    geojson = base / "targets" / "area.geojson"
    relative_source = base / "imagery" / "20260613"
    absolute_source = tmp_path / "lan_like" / "20260613"
    output = base / "downloaded"
    geojson.parent.mkdir(parents=True)
    relative_source.mkdir(parents=True)
    absolute_source.mkdir(parents=True)
    output.mkdir()
    geojson.write_text('{"type": "Point", "coordinates": [0, 0]}', encoding="utf-8")

    request = SatelliteDownloadRequest(
        geojson_files=[Path("targets") / "area.geojson"],
        image_folders=[Path("imagery") / "20260613", absolute_source],
        output_dir=Path("downloaded"),
        base_dir=base,
        extensions=[".tif", ".tiff"],
        filename_formats=[
            DownloadFilenameFormatRule(
                name="planet",
                raw_format="PSScene_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tif",
                max_cloud_percent=90,
            )
        ],
    )

    resolved = resolve_download_request(request)

    assert resolved.geojson_files == (geojson.resolve(),)
    assert [folder.name for folder in resolved.image_folders] == ["20260613", "20260613_2"]
    assert [folder.path for folder in resolved.image_folders] == [
        relative_source.resolve(),
        absolute_source.resolve(),
    ]
    assert resolved.output_dir == output.resolve()
    assert resolved.extensions == frozenset({".tif", ".tiff"})
    assert resolved.filename_formats[0].max_cloud_percent == 90


@pytest.mark.parametrize(
    ("download_request", "field_name", "message"),
    [
        (
            SatelliteDownloadRequest(
                geojson_files=[],
                image_folders=["images"],
                output_dir="out",
            ),
            "geojson_files",
            "Chưa chọn file GeoJSON",
        ),
        (
            SatelliteDownloadRequest(
                geojson_files=["missing.geojson"],
                image_folders=["images"],
                output_dir="out",
            ),
            "geojson_files[1]",
            "File GeoJSON không tồn tại",
        ),
        (
            SatelliteDownloadRequest(
                geojson_files=["target.geojson"],
                image_folders=[],
                output_dir="out",
            ),
            "image_folders",
            "Chưa chọn folder ảnh",
        ),
        (
            SatelliteDownloadRequest(
                geojson_files=["target.geojson"],
                image_folders=["missing"],
                output_dir="out",
            ),
            "image_folders[1]",
            "Folder ảnh đầu vào không tồn tại",
        ),
        (
            SatelliteDownloadRequest(
                geojson_files=["target.geojson"],
                image_folders=["images"],
                output_dir="out",
                extensions=["tif"],
            ),
            "extensions[1]",
            "phải bắt đầu bằng dấu chấm",
        ),
    ],
)
def test_resolve_download_request_reports_vietnamese_config_errors(
    tmp_path: Path,
    download_request: SatelliteDownloadRequest,
    field_name: str,
    message: str,
) -> None:
    (tmp_path / "target.geojson").write_text(
        '{"type": "Point", "coordinates": [0, 0]}',
        encoding="utf-8",
    )
    (tmp_path / "images").mkdir()
    download_request.base_dir = tmp_path

    with pytest.raises(SatelliteDownloadConfigError) as exc_info:
        resolve_download_request(download_request)

    assert exc_info.value.field_name == field_name
    assert message in str(exc_info.value)


def test_resolve_download_request_rejects_output_inside_source_folder(tmp_path: Path) -> None:
    geojson = tmp_path / "target.geojson"
    source = tmp_path / "images"
    output = source / "downloaded"
    geojson.write_text('{"type": "Point", "coordinates": [0, 0]}', encoding="utf-8")
    source.mkdir()

    request = SatelliteDownloadRequest(
        geojson_files=[geojson],
        image_folders=[source],
        output_dir=output,
    )

    with pytest.raises(SatelliteDownloadConfigError) as exc_info:
        resolve_download_request(request)

    assert exc_info.value.field_name == "output_dir"
    assert "Không đặt output trong folder ảnh đầu vào" in str(exc_info.value)


def test_resolve_download_request_does_not_create_output_folder(tmp_path: Path) -> None:
    geojson = tmp_path / "target.geojson"
    source = tmp_path / "images"
    output = tmp_path / "new-output"
    geojson.write_text('{"type": "Point", "coordinates": [0, 0]}', encoding="utf-8")
    source.mkdir()

    resolved = resolve_download_request(
        SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=output,
        )
    )

    assert resolved.output_dir == output.resolve()
    assert not output.exists()
