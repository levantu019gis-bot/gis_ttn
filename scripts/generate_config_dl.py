import argparse
import copy
import json
import re
import unicodedata
from pathlib import Path


DEFAULT_SCALE = 50000
DEFAULT_OUTPUT = "config_DL.generated.json"
DEFAULT_COMMENT = (
    "Kh\u00f4ng ghi nh\u1eadn ho\u1ea1t \u0111\u1ed9ng t\u00f4n t\u1ea1o, "
    "x\u00e2y d\u1ef1ng c\u00f4ng tr\u00ecnh."
)


PREFIX_RE = re.compile(r"^(?P<group>\d+)\.(?P<item>\d+)\.(?P<name>.+)$")


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_geojson_name(path):
    stem = path.stem
    match = PREFIX_RE.match(stem)
    if not match:
        return {
            "display_name": stem,
            "group_key": "khac",
            "group_title": "Nh\u00f3m kh\u00e1c",
            "sort_key": (999999, 999999, stem.lower()),
        }

    group_number = int(match.group("group"))
    item_number = int(match.group("item"))
    display_name = match.group("name").strip()
    return {
        "display_name": display_name,
        "group_key": str(group_number),
        "group_title": f"Nh\u00f3m {group_number}",
        "sort_key": (group_number, item_number, display_name.lower()),
    }


def slugify(value):
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_")
    return slug or "target"


def unique_id(base_id, used_ids):
    candidate = base_id
    counter = 2
    while candidate in used_ids:
        candidate = f"{base_id}_{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def iter_positions(coordinates):
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        yield coordinates
        return

    if isinstance(coordinates, list):
        for item in coordinates:
            yield from iter_positions(item)


def geometry_center(geometry):
    positions = list(iter_positions(geometry.get("coordinates", [])))
    if not positions:
        raise ValueError("Geometry has no coordinates")

    lons = [float(point[0]) for point in positions]
    lats = [float(point[1]) for point in positions]
    return [
        round((min(lons) + max(lons)) / 2, 8),
        round((min(lats) + max(lats)) / 2, 8),
    ]


def first_geometry(geojson_path):
    data = load_json(geojson_path)
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{geojson_path.name}: expected FeatureCollection")

    features = data.get("features") or []
    if not features:
        raise ValueError(f"{geojson_path.name}: no features found")

    geometry = features[0].get("geometry")
    if not geometry:
        raise ValueError(f"{geojson_path.name}: first feature has no geometry")

    return geometry


def update_export(export_config, display_name):
    export_config = copy.deepcopy(export_config)
    export_config["template_txt_value"] = (
        f"T\u1ea1i {display_name} (l\u00fac {{time_label}}, "
        f"\u0111\u1ed9 ph\u00e2n gi\u1ea3i 3 m): {DEFAULT_COMMENT}"
    )

    for placeholder in export_config.get("placeholders", []):
        if placeholder.get("field") == "title":
            placeholder["value"] = (
                f"Hi\u1ec7n tr\u1ea1ng {display_name} ng\u00e0y {{capture_date}}"
            )
        elif placeholder.get("field") == "comment":
            placeholder["value"] = DEFAULT_COMMENT

    return export_config


def build_target(template_target, geojson_path, info, sort_order, scale, used_ids):
    display_name = info["display_name"]
    geometry = first_geometry(geojson_path)

    target = copy.deepcopy(template_target)
    target["id"] = unique_id(slugify(display_name), used_ids)
    target["enabled"] = True
    target["group"] = {
        "key": info["group_key"],
        "title": info["group_title"],
    }
    target["sort_order"] = sort_order
    target["name"] = display_name
    target["alias"] = display_name
    target["coordinate"] = geometry_center(geometry)
    target["scale"] = scale
    target["metadata"] = {
        **copy.deepcopy(target.get("metadata", {})),
        "geojson_geometry": geometry,
    }

    if "export" in target:
        target["export"] = update_export(target["export"], display_name)

    return target


def collect_geojson_files(base_dir, output_path):
    ignored = {output_path.name.lower()}
    return [
        path
        for path in base_dir.glob("*.geojson")
        if path.name.lower() not in ignored
    ]


def generate_config(template_path, output_path, scale):
    base_dir = template_path.parent
    template = load_json(template_path)
    template_targets = template.get("targets") or []
    if not template_targets:
        raise ValueError(f"{template_path.name}: no template target found")

    geojson_infos = []
    for geojson_path in collect_geojson_files(base_dir, output_path):
        info = parse_geojson_name(geojson_path)
        geojson_infos.append((info["sort_key"], geojson_path, info))

    geojson_infos.sort(key=lambda item: item[0])

    used_ids = set()
    generated_targets = []
    for sort_order, (_, geojson_path, info) in enumerate(geojson_infos, start=1):
        generated_targets.append(
            build_target(
                template_targets[0],
                geojson_path,
                info,
                sort_order,
                scale,
                used_ids,
            )
        )

    output = copy.deepcopy(template)
    output["targets"] = generated_targets
    save_json(output_path, output)
    return len(generated_targets)


def main():
    parser = argparse.ArgumentParser(
        description="Generate config_DL targets from GeoJSON files."
    )
    parser.add_argument(
        "--template",
        default="config_DL.json",
        help="Template config file. Default: config_DL.json",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output config file. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=DEFAULT_SCALE,
        help=f"Target scale. Default: {DEFAULT_SCALE}",
    )
    args = parser.parse_args()

    template_path = Path(args.template).resolve()
    output_path = Path(args.output).resolve()

    count = generate_config(template_path, output_path, args.scale)
    print(f"Generated {count} targets: {output_path}")


if __name__ == "__main__":
    main()
