---
stepsCompleted: [1]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'LAN satellite image extraction tool: desktop vs web'
research_goals: 'Chon kien truc toi uu de nhan GeoJSON AOI va folder anh ve tinh tren server LAN, sau do xuat cac anh/crop tai khu vuc quan tam ve may local; app khong duoc cai tren may chu luu anh'
user_name: 'Ongtu'
date: '2026-06-09'
web_research_enabled: true
source_verification: true
---

# Research Report: LAN Satellite Image Extraction Tool

**Date:** 2026-06-09  
**Author:** Ongtu  
**Research Type:** Technical

---

## Rang Buoc Cap Nhat

Khong the cai app/backend/worker tren may chu luu anh. App chi co the cai tren may local cua nguoi dung hoac mot may khac trong LAN. Vi vay khong the toi uu bang cach dua compute truc tiep len server anh; phuong an toi uu tiep theo la dat **mot may xu ly tap trung trong LAN** co ket noi mang tot toi server anh.

## Tom Tat Ket Luan

Khuyen nghi toi uu trong rang buoc moi la **web app noi bo + backend/worker cai tren mot may xu ly trong LAN**, khong cai tren server anh. May nay mount/truy cap read-only folder anh tren `192.168.100.234`, xu ly bang GDAL/Rasterio, roi tra ket qua cho nguoi dung.

Neu chi co mot nguoi dung, co the lam **desktop app local**. Neu co nhieu nguoi dung hoac job nang, nen lam **web app cai tren mot workstation/mini server rieng trong LAN**.

Neu nguoi dung can chon output folder truc tiep tren may local, nen dung **desktop app local** hoac **mo hinh lai**:

- Worker/web backend tren may xu ly trong LAN: index anh, tim anh giao voi AOI, clip/crop, nen ZIP/COG/GeoTIFF output.
- UI web noi bo de upload/chon GeoJSON, chon folder anh, theo doi job.
- Tuy chon desktop downloader mong nhe neu bat buoc ghi truc tiep vao folder local thay vi download ZIP qua trinh duyet.

Ly do: khi khong duoc cai tren server anh, ta khong loai bo duoc viec doc du lieu qua LAN. Muc tieu luc nay la **doc qua LAN it nhat co the**, **khong lap lai tren nhieu may client**, va **index truoc metadata/footprint** de tranh scan toan bo kho anh moi lan chay.

---

## Bai Toan

**Input**

- Mot hoac nhieu file GeoJSON mo ta khu vuc quan tam.
- Mot hoac nhieu folder anh ve tinh tren server LAN, vi du `192.168.100.234/data/satellite_imgage`.

**Output**

- Folder ket qua gom anh ve tinh ung voi khu vuc quan tam.
- Can xac dinh ro output la:
  - `copy`: copy nguyen file anh nao giao voi AOI.
  - `clip`: cat/crop raster theo polygon AOI.
  - `both`: copy metadata + tao raster da clip.

Trong da so truong hop GIS thuc te, nen mac dinh la **clip/crop theo AOI**, vi cau "anh ve tinh tai cac khu vuc quan tam" ham y khong can copy toan bo tile/canh anh.

---

## Nen Desktop Hay Web?

### 1. Desktop-only

Mo hinh: app PySide/PyQt/Tauri/Electron cai tren may nguoi dung, doc folder LAN qua SMB/NFS/HTTP, xu ly bang GDAL/Rasterio, ghi output vao local folder.

**Uu diem**

- Chon folder local va ghi file rat tu nhien.
- De lam ban dau neu chi co 1-2 nguoi dung.
- Co the chay offline neu da mount duoc folder anh.

**Nhuoc diem**

- Moi client phai cai GDAL/Rasterio va dependency GIS, de loi moi truong.
- Moi may doc anh lon qua LAN, gay nghen mang khi nhieu nguoi cung chay.
- Kho quan ly queue, retry, log, audit.
- Kho cap nhat phien ban dong nhat.

**Phu hop khi**

- It nguoi dung.
- Du lieu khong qua lon.
- Khong muon cai server/backend.
- Chap nhan toc do phu thuoc may ca nhan va LAN.

### 2. Web thuần trong browser

Mo hinh: browser upload GeoJSON, doc folder/anh va xu ly ngay trong client.

**Khong khuyen nghi.**

Browser co the dung File System Access API trong mot so moi truong, nhung kha nang truy cap/ghi file local va network folder bi gioi han boi bao mat, phu thuoc trinh duyet va HTTPS. Xu ly raster lon trong browser cung khong phai duong toi uu vi GDAL/Rasterio ecosystem manh hon o backend.

**Phu hop khi**

- Chi preview nhe.
- Khong xu ly raster lon.
- Chap nhan download ZIP thay vi ghi truc tiep folder.

### 3. Web app noi bo co backend/worker tren may xu ly LAN

Mo hinh: backend chay tren mot may local/workstation/mini server trong LAN, khong phai may chu anh. May nay truy cap `192.168.100.234/data/satellite_imgage` qua SMB/NFS/HTTP hoac mount path noi bo. Nguoi dung dung browser de upload GeoJSON/chon folder/chay job. Backend dung GDAL/Rasterio/GeoPandas de tim anh giao AOI va tao output.

**Uu diem**

- Tap trung xu ly tren mot may co cau hinh va ket noi LAN tot.
- Centralize dependency GIS: chi may xu ly LAN can cai GDAL/Rasterio.
- De co job queue, retry, progress, log.
- Nhieu nguoi dung dung chung, cap nhat mot noi.
- Co the index truoc footprint/metadata de tim anh nhanh.

**Nhuoc diem**

- Van phai doc raster qua LAN tu may chu anh.
- Can trien khai service noi bo tren may xu ly LAN.
- Output ve may local thuong la download ZIP hoac sync; browser khong phai luc nao cung ghi duoc vao folder tuy y.

**Phu hop nhat khi**

- Anh lon, nhieu folder, nhieu lan chay.
- Co nhieu nguoi dung.
- Can on dinh, co log, co kha nang mo rong.

### 4. Mo hinh lai: web backend + desktop downloader

Mo hinh: backend xu ly tren may xu ly LAN; desktop app cuc mong chi lam viec:

- dang nhap/ket noi backend LAN,
- chon GeoJSON/folder output local,
- gui job len backend,
- nhan danh sach output va tai ve dung folder local.

**Day la lua chon toi uu neu co nhieu nguoi dung va yeu cau "output la folder local" la bat buoc.**

Core compute nam tren may xu ly LAN, con desktop chi giai quyet trai nghiem local filesystem.

---

## Kien Truc De Xuat

### Phien ban MVP nen lam

1. **May xu ly LAN**
   - Cai app tren mot workstation/mini server trong LAN, khong phai may chu anh.
   - Mount folder anh tu `192.168.100.234` o che do read-only neu co the.
   - Uu tien ket noi day 1GbE/10GbE thay vi Wi-Fi.

2. **Backend API noi bo**
   - FastAPI hoac Django.
   - Endpoint upload GeoJSON, chon folder anh, tao job.
   - Endpoint xem progress, tai ket qua.

3. **Worker xu ly GIS**
   - GDAL CLI hoac Rasterio.
   - Neu can job dai: RQ/Celery + Redis.
   - Neu MVP don gian: worker process noi bo + job table SQLite/PostgreSQL.

4. **Index anh**
   - Quet folder anh, doc footprint/bounds/CRS/date/cloud cover neu co.
   - Luu vao PostGIS neu du lieu lon/nhieu nguoi dung.
   - Dung GeoPackage/SQLite RTree neu MVP nho gon.

5. **Pipeline job**
   - Validate GeoJSON.
   - Chuan hoa CRS AOI theo CRS anh.
   - Spatial query: tim raster giao voi AOI.
   - Clip/crop tung raster.
   - Ghi output vao job folder tren server.
   - Nen ket qua thanh ZIP de nguoi dung tai ve.

6. **UI**
   - Upload GeoJSON.
   - Chon dataset/folder anh da index.
   - Nut Run.
   - Bang progress/log.
   - Download output.

### Neu can folder local thay vi ZIP download

Them desktop app nhe:

- Tauri/Electron hoac Python PySide.
- App chon output folder local.
- App goi API backend.
- Backend tra ve manifest file ket qua.
- App tai file ve va ghi vao folder da chon.

Khong nen de moi desktop client tu doc va crop anh LAN neu co nhieu nguoi dung, vi moi may se lap lai viec doc raster lon qua LAN.

---

## Xu Ly Dia Ly Va Raster

### GeoJSON

GeoJSON theo RFC 7946 bieu dien Geometry, Feature, FeatureCollection va ho tro Polygon/MultiPolygon. Can luu y toa do GeoJSON thuong la WGS84, thu tu `[longitude, latitude]`.

### Clip/crop raster

Co hai cach kha on dinh:

- **GDAL**: `gdalwarp -cutline aoi.geojson -crop_to_cutline ...`
- **Rasterio**: `rasterio.mask.mask(src, shapes, crop=True)`

Nen uu tien GDAL CLI cho pipeline batch vi on dinh, de log lenh, de reproduce. Rasterio phu hop neu can logic Python tuy bien nhieu hon.

### Dinh dang output

- GeoTIFF neu can giu georeference day du.
- Cloud Optimized GeoTIFF neu ve sau can truy cap partial qua HTTP/range request.
- JPEG/PNG chi nen dung cho quicklook/preview, khong nen lam output chinh neu can GIS metadata.

---

## Quyet Dinh Cuoi

**Quyet dinh sau khi chot pham vi:** lam **mot script Python config-driven** chay tren may local hoac mot may xu ly trong LAN. Script doc file config JSON gom folder GeoJSON, cac folder anh tren server LAN, va output folder; sau do scan anh, tim anh giao voi AOI, copy anh phu hop ve output, hien thi tien trinh trong command line.

Day la phuong an gon nhat cho giai doan dau vi:

- Khong can cai dat gi tren may chu anh.
- Khong can dung web/desktop UI khi workflow co the batch qua config.
- De kiem soat loi cau hinh/duong dan ngay tu dau.
- De chay lai, log, va nang cap ve sau thanh desktop/web neu can.

**Phuong an nang cap sau:** chon web app noi bo + backend/worker tren mot may xu ly trong LAN neu co nhieu nguoi dung, job nang, can queue/progress UI/log tap trung.

**Chon desktop-only** neu chi co mot nguoi dung, job khong qua nang, va uu tien cai dat don gian/giai quyet nhanh.

**Them desktop downloader** neu dung web backend tap trung nhung yeu cau ghi truc tiep vao folder local quan trong hon viec download ZIP.

Khong nen chon:

- **Desktop-only cho nhieu nguoi dung** neu du lieu lon, vi se doc anh qua LAN lap lai va kho quan ly dependency.
- **Web thuần browser-only** vi bi gioi han local filesystem va khong toi uu cho raster processing nang.

---

## Roadmap De Xuat

### Phase 1: Prototype CLI

- Viet script Python/CLI nhan:
  - `--geojson`
  - `--image-root`
  - `--output`
  - `--mode copy|clip|both`
- Dung GDAL/Rasterio de chay end-to-end tren 10-50 anh mau.
- Do toc do va dung luong output.

### Phase 2: Index

- Quet folder anh, tao bang metadata.
- Luu path, bounds, CRS, resolution, acquisition date.
- Spatial query AOI de tranh scan toan bo folder moi lan.

### Phase 3: Web Internal App

- UI upload GeoJSON, chon dataset, tao job.
- Worker chay async.
- Download ZIP output.

### Phase 4: Desktop Downloader Neu Can

- Dong goi app mong cho Windows/Linux.
- Chon output local folder.
- Goi backend va sync output.

---

## Nguon Tham Khao

- GeoJSON RFC 7946: https://www.rfc-editor.org/rfc/rfc7946
- GDAL `gdalwarp`: https://gdal.org/en/stable/programs/gdalwarp.html
- GDAL `gdal raster clip`: https://gdal.org/en/stable/programs/gdal_raster_clip.html
- GDAL Virtual File Systems va HTTP range request: https://gdal.org/en/stable/user/virtual_file_systems.html
- Rasterio mask API: https://rasterio.readthedocs.io/en/stable/api/rasterio.mask.html
- QGIS Clip raster by mask layer, derived from GDAL warp: https://documentation.qgis.org/3.44/ru/docs/user_manual/processing_algs/gdal/rasterextraction.html
- MDN File System API: https://developer.mozilla.org/docs/Web/API/File_System_API
- GeoServer WCS basics: https://docs.geoserver.org/main/en/user/services/wcs/basics/
- OGC STAC overview: https://www.ogc.org/standards/stac/
