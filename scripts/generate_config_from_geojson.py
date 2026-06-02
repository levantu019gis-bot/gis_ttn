#!/usr/bin/env python3
"""Generate project config.json from target GeoJSON files."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from thucthengay.models import ProjectConfig  # noqa: E402


def relative_path(path: Path, base_dir: Path) -> str:
    return os.path.relpath(path, base_dir).replace("\\", "/")


def read_geojson(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if data.get("type") != "Feature":
        raise ValueError(f"{path} phải là GeoJSON Feature.")
    properties = data.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(f"{path} thiếu object properties.")
    geometry = data.get("geometry")
    if not isinstance(geometry, dict):
        raise ValueError(f"{path} thiếu object geometry.")
    return data


def lon_lat_from_center(path: Path, properties: dict[str, Any]) -> list[float]:
    center = properties.get("center")
    if (
        not isinstance(center, list)
        or len(center) != 2
        or not all(isinstance(value, int | float) for value in center)
    ):
        raise ValueError(f"{path} thiếu properties.center dạng [lat, lon].")

    lat = float(center[0])
    lon = float(center[1])
    return [lon, lat]


def target_from_geojson(
    path: Path,
    *,
    config_dir: Path,
    template_pptx_file: Path,
    map_element_id: int,
    scale: int,
    grid_minutes: int,
) -> dict[str, Any]:
    data = read_geojson(path)
    properties = data["properties"]
    geometry = data["geometry"]
    source_name = str(properties.get("name") or path.stem)
    display_name = str(properties.get("alias") or source_name)
    sort_order_raw = properties.get("id", 0)

    try:
        sort_order = int(sort_order_raw)
    except (TypeError, ValueError):
        sort_order = 0

    return {
        "id": source_name,
        "enabled": True,
        "sort_order": sort_order,
        "name": display_name,
        "alias": display_name,
        "title": display_name,
        "geojson_file": relative_path(path, config_dir),
        "coordinate": lon_lat_from_center(path, properties),
        "scale": scale,
        "grid": {
            "interval": {"degrees": 0, "minutes": grid_minutes, "seconds": 0},
            "label_format": "dms_full",
            "style": {
                "frame_color": "#000000",
                "label_color": "#000000",
                "label_font_size": 10,
                "tick_length_px": 8,
            },
        },
        "export": {
            "template_pptx_file": relative_path(template_pptx_file, config_dir),
            "template_txt_value": "Tại {target_title} (lúc {time_label}, độ phân giải 3 m): ",
            "date_format": "dd.MM.yy",
            "time_format": "HH.mm/dd.MM.yy",
            "map_background_color": "#FFFFFF",
            "placeholders": [
                {
                    "field": "map_image",
                    "kind": "map_image",
                    "element_id": map_element_id,
                    "required": True,
                }
            ],
        },
        "metadata": {
            "geojson_type": data.get("type"),
            "geojson_geometry_type": geometry.get("type"),
            "geojson_properties": properties,
            "geojson_geometry": geometry,
            "source_geojson_file": relative_path(path, config_dir),
            "source_center_order": "lat_lon",
        },
    }


def build_config(
    geojson_dir: Path,
    *,
    output_path: Path,
    template_pptx_file: Path,
    map_element_id: int,
    scale: int,
    grid_minutes: int,
) -> ProjectConfig:
    files = sorted(geojson_dir.glob("*.geojson"))
    if not files:
        raise ValueError(f"Không tìm thấy *.geojson trong {geojson_dir}")

    config_dir = output_path.parent
    targets = [
        target_from_geojson(
            path.resolve(),
            config_dir=config_dir,
            template_pptx_file=template_pptx_file.resolve(),
            map_element_id=map_element_id,
            scale=scale,
            grid_minutes=grid_minutes,
        )
        for path in files
    ]
    targets.sort(key=lambda target: (target["sort_order"], target["id"]))
    return ProjectConfig(schema_version="1.0", targets=targets)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate config.json from target GeoJSON files."
    )
    parser.add_argument(
        "geojson_dir",
        type=Path,
        default=Path("webapp_geojson/output_geojson"),
        nargs="?",
        help="Directory containing one GeoJSON Feature per target.",
    )
    parser.add_argument("--output", type=Path, default=Path("config.json"))
    parser.add_argument(
        "--template-pptx",
        type=Path,
        default=Path("examples/templates/target_001.template.pptx"),
        help="One-slide PPTX template shared by all targets unless edited later.",
    )
    parser.add_argument("--map-element-id", type=int, default=65)
    parser.add_argument("--scale", type=int, default=50000)
    parser.add_argument("--grid-minutes", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output_path = args.output.resolve()
    config = build_config(
        args.geojson_dir.resolve(),
        output_path=output_path,
        template_pptx_file=args.template_pptx.resolve(),
        map_element_id=args.map_element_id,
        scale=args.scale,
        grid_minutes=args.grid_minutes,
    )
    output_path.write_text(
        json.dumps(config.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} ({len(config.targets)} targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
