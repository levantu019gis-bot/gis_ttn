# Thiet Ke Tach Project Config Va Application Settings

Ngay lap: 2026-06-14

## Muc Tieu

Thay doi cau truc cau hinh de file `config.json` cua du an chi chua thong tin target. Cac tham so dung chung nhu `defaults`, `historical_registry`, `historical_loading`, va `filename_patterns` se duoc tach rieng thanh application settings di cung phan mem.

Muc tieu ky thuat la giam do phuc tap cua project config, quan ly thiet lap dung chung tap trung theo phan mem, nhung van giu tuong thich nguoc voi config cu va khong lam anh huong ingestion/render/export.

## Hien Trang

Runtime hien dang doc truc tiep raw `config.json` va validate bang `ProjectConfig` trong `src/thucthengay/config/service.py`.

`ProjectConfig` hien chua day du cac section:

- `schema_version`
- `defaults`
- `historical_registry`
- `historical_loading`
- `filename_patterns`
- `targets`

Logic apply defaults vao target hien nam trong validator cua `ProjectConfig`. Vi vay khong nen xoa cac field nay khoi runtime model ngay. Thay vao do, can tach format luu tru ben ngoai va giu mot object runtime da compose day du.

Config editor hien luu draft raw va save nguyen draft ra `config.json`, nen neu muon target-only config thi can tach state cua editor thanh project draft va settings draft.

## Dinh Huong Kien Truc

Giu `ProjectConfig` lam model runtime da compose. Them cac model/document moi:

- `ProjectConfigDocument`: schema file project target-only.
- `AppSettingsConfig`: schema application settings.
- `AppSettingsProfile`: mot profile settings gom defaults, historical, filename patterns.
- `ProjectConfig`: tiep tuc la composed runtime config cho cac module hien tai.

Luon thuc hien compose truoc khi validate runtime:

```text
packaged app settings
< user app settings
< legacy project sections
< target-level overrides
```

Trong do:

- Packaged app settings la default di cung phan mem.
- User app settings la cau hinh co the sua qua UI.
- Legacy project sections la cac section `defaults`, `historical_*`, `filename_patterns` neu file config cu van co.
- Target-level overrides trong tung target van co uu tien cao nhat.

## Cau Truc File De Xuat

Project config moi:

```json
{
  "schema_version": "2.0",
  "settings_profile": "default",
  "targets": []
}
```

Application settings:

```json
{
  "schema_version": "1.0",
  "profiles": {
    "default": {
      "defaults": {},
      "historical_registry": {},
      "historical_loading": {},
      "filename_patterns": []
    }
  }
}
```

Vi tri file de xuat:

- Packaged default: `src/thucthengay/resources/app_settings.default.json`
- User override: `%APPDATA%/ThucTheNgay/app_settings.json`
- Project config: file user chon, vi du `2.Data/examples/config.json`

## Path Resolution

Can tach ro path theo nguon:

Project-relative paths:

- `target.geojson_file`
- `target.export.template_pptx_file`
- `historical_registry.database_path`

App-resource paths:

- font bundled mac dinh neu di cung app resources
- cac asset thuc su thuoc phan mem

Khuyen nghi quan trong: `historical_registry.database_path` du nam trong app settings van nen resolve relative theo project config directory, khong resolve theo app install dir. Ly do la SQLite history la du lieu lam viec, khong nen ghi vao thu muc cai dat phan mem.

## Runtime Loader

Them module moi trong `src/thucthengay/config/`, vi du `settings_service.py`.

Public API de xuat:

```python
def load_app_settings(profile: str = "default") -> AppSettingsProfile: ...

def compose_project_config(
    raw_project: dict[str, Any],
    settings: AppSettingsProfile,
) -> dict[str, Any]: ...
```

Sua `load_project_config(config_path)`:

```text
raw_project = load_json_file(config_path)
profile = raw_project.get("settings_profile", "default")
settings = load_app_settings(profile)
composed_raw = compose_project_config(raw_project, settings)
result.config = ProjectConfig.model_validate(_enabled_targets_only(composed_raw))
```

Sua `read_historical_loading_settings(config_path)` de dung composed config, khong doc raw `historical_loading` truc tiep tu project config nua.

Sua `update_target_alignment_defaults(config_path, ...)` de:

- Chi cap nhat target trong project config.
- Validate sau update bang composed config.
- Khong them `defaults`, `historical`, `filename_patterns` vao project config target-only.

## Config Editor

Nen tach UI thanh hai nhom khai niem:

Project Config:

- Targets
- Target inspector
- Raw Project JSON

Application Settings:

- Defaults
- Historical
- Filename Patterns
- Raw Settings JSON

`ConfigEditorService` nen tach state:

- `project_draft`
- `project_persisted`
- `settings_draft`
- `settings_persisted`

Save behavior:

- Target changes ghi vao `config.json`.
- Defaults/Historical/Filename Patterns ghi vao user app settings.
- Neu file config la legacy full config, mac dinh nen giu nguyen format cu cho den khi user chon migrate/export target-only.

UI can hien thi nguon du lieu:

- `Project target config`
- `Application settings profile: default`
- Neu legacy config co embedded settings: hien canh bao `File nay dang chua legacy settings`.

## Tuong Thich Nguoc

Ho tro ba truong hop:

1. Legacy full config co `defaults`, `historical_*`, `filename_patterns`, `targets`.
   - Load duoc.
   - Legacy sections duoc coi la project override.
   - Save mac dinh giu nguyen full config de khong mat thong tin.

2. New target-only config chi co `targets`.
   - Load settings tu app profile.
   - Save chi ghi target config.

3. Migrate/export target-only.
   - Them action rieng, chi thuc hien khi user xac nhan.
   - Tach settings tu legacy config sang app settings/user profile.
   - Ghi lai project config moi chi chua targets va `settings_profile`.

## Rui Ro Can Kiem Soat

- Neu `filename_patterns` khong duoc compose truoc ingestion, parser filename co the sai hoac fallback rong.
- Neu Setup tab van doc raw `historical_loading`, checkbox load historical se sai voi app settings.
- Neu `historical_registry.database_path` resolve theo app settings file, app co the ghi DB vao thu muc cai dat hoac thu muc khong co quyen.
- Neu Config tab tiep tuc save settings vao project config, muc tieu target-only se khong dat.
- Neu validate raw project config target-only truc tiep bang `ProjectConfig` thi default factory cua model co the khong du de phan anh app settings that.

## Ke Hoach Trien Khai

1. Them `resources/app_settings.default.json`.
2. Them model `AppSettingsConfig`, `AppSettingsProfile`, `ProjectConfigDocument`.
3. Them compose service trong `config/settings_service.py`.
4. Sua `load_project_config` dung composed config.
5. Sua `read_historical_loading_settings` dung composed config.
6. Sua `update_target_alignment_defaults` validate bang composed config nhung chi ghi target vao project config.
7. Sua `ConfigEditorService` tach project draft va settings draft.
8. Sua Config tab theo hai nhom Project Config va Application Settings.
9. Them migrate/export target-only cho legacy config.
10. Cap nhat tests.

## Test Can Co

- Target-only config load duoc va runtime nhan du `defaults`, `historical`, `filename_patterns`.
- Legacy full config giu dung hanh vi hien tai.
- Legacy embedded settings override packaged/user app settings.
- User app settings override packaged app settings.
- `historical_registry.database_path` resolve theo project config directory.
- Filename parser dung patterns tu app settings khi project config khong co `filename_patterns`.
- Setup tab doc dung historical loading tu composed config.
- Config tab save target-only config khong ghi lai defaults/historical/patterns vao project config.
- `update_target_alignment_defaults` chi thay doi target fields.

## Ket Luan

Nen thuc hien theo huong target-only project config, nhung khong xoa ngay `ProjectConfig` day du. Cach an toan nhat la them lop compose settings truoc validation va giu `ProjectConfig` lam runtime composed model. Thay doi format luu tru nen co migration ro rang va tuong thich nguoc voi config cu.
