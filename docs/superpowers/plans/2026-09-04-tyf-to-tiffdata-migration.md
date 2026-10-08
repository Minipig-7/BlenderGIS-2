# План: завершение миграции Tyf → tiffdata

> **Для агентов-исполнителей:** шаги используют чекбоксы. Перед Шагом 1 оркестратор выполняет пре-чек из раздела «Grep-запросы».

**Сложность: средняя (с уклоном в низкую).** Кода мало (3 файла + удаление вендорной папки), но перед правками обязательна runtime-верификация семантики tiffdata 0.5.7: `get()` возвращает `None` при отсутствии тега (не бросает `KeyError`) и бросает `TypeError` на неопознанной строке — мигрированный код местами рассчитан на поведение Tyf.

**Цель:** убрать последние следы Tyf — переименовать `GeoRef.fromTyf`, починить обработку ошибок под реальную семантику tiffdata, удалить вендорный `core/lib/Tyf/`, обновить AGENTS.md.

**Фактическое состояние (проверено grep'ом по всему репо):**
- Импортов модуля Tyf **не осталось** (`(from|import)\s+Tyf` → 0 совпадений).
- `operators/add_camera_exif.py:38` — уже на tiffdata, но `except KeyError` (строки 148–153, 156–159, 168–171, 201–204) не сработает: `get()` возвращает `None`, а не бросает `KeyError`; неопознанная строка даёт `TypeError`.
- `core/georaster/georef.py` — импорт tiffdata есть, но: метод ещё зовётся `fromTyf` (стр. 87), мёртвый `except KeyError` (стр. 129–135), устаревший комментарий `# geotags = Tyf.gkd.Gkd(tif)` (стр. 127), `get()` без `first=True` для одиночных тегов (стр. 96, 101, 103).
- `core/georaster/georaster.py:189` — вызов `GeoRef.fromTyf(tiff)`; стр. 183–185: `assert isinstance(nodata, str)` упадёт с `AssertionError`, если тега GDALNoData нет.
- Вендорный `core/lib/Tyf/` — мёртвый груз (0 импортов).
- Зависимости чисты: `tiffdata>=0.5.7` в `requirements.txt` и `pyproject.toml`, Tyf там отсутствует.
- ВАЖНО: маппинг в `docs/...2026-07-19-*.md` (`Tyf.TiffFile → tiffdata.TiffFile`) устарел — фактический API tiffdata 0.5.7 это `tiffdata.TIFF`. Исторические документы НЕ правим.

## Global Constraints
- Отступы: `georef.py`, `georaster.py` — пробелы; `add_camera_exif.py` — пробелы в телах классов, **табы** в `register()/unregister()` внизу файла. Не переформатировать.
- `.opencode/` не трогать (автогенерируется; упоминания Tyf в `.opencode/agents/*.md` остаются).
- `docs/superpowers/specs|plans/2026-07-19-*` — история, не править.
- `opencode.jsonc` не трогать.
- Репозиторий не является git-репо — шагов коммита нет; проверка через py_compile + grep + ручной тест в Blender.
- НЕ оптимизировать логику во время миграции — только замена/починка семантики вызовов.

---

### Шаг 0: Пре-чек оркестратора (перед запуском шагов)
- [ ] `Glob **/*.{tif,tiff}` и `Glob **/*.{jpg,jpeg}` — найти тестовые фикстуры (GeoTIFF с геотегами + геотегированный JPEG). Если фикстур нет — запросить у пользователя; без GeoTIFF-фикстуры Шаг 1 проверит только поведение «тег отсутствует», но не структуру `values` геотегов.

### Шаг 1: [core-agent] → `C:\Temp\opencode\tiffdata_semantics_check.py` → runtime-верификация семантики tiffdata
Блокирует Шаги 2 и 3. Скрипт запускается вне Blender (в `.venv` есть tiffdata 0.5.7 и pillow).

- [ ] Создать `C:\Temp\opencode\tiffdata_semantics_check.py`:

```python
# -*- coding: utf-8 -*-
"""Проверка семантики tiffdata 0.5.7 для завершения миграции Tyf -> tiffdata.
Запуск: uv run python tiffdata_semantics_check.py [optional_geotiff.tif]
"""
import os
import sys
import tempfile

from PIL import Image
from tiffdata import TIFF, TIFFTag

print("=== tiffdata semantics check ===")

# 1. Отсутствующий тег -> None или исключение?
p = os.path.join(tempfile.gettempdir(), "bgis_plain.tif")
Image.new("L", (4, 4)).save(p)
t = TIFF(p)
print("ImageWidth(first=True):", repr(t.get(TIFFTag.ImageWidth, first=True)))
print("Missing GDALNoData:", repr(t.get(TIFFTag.GDALNoData, first=True)))
print("Missing GeoKeyDirectory:", repr(t.get(TIFFTag.GeoKeyDirectoryTag)))

# 2. Строковый ключ: неизвестное имя -> TypeError? известное, но отсутствующее -> None?
for key in ("GPSLatitude", "GPSLatitudeRef", "GPSLongitude", "GPSLongitudeRef",
            "GPSAltitude", "FocalLengthIn35mmFilm", "Orientation", "NoSuchTagXYZ"):
    try:
        v = t.get(key)
        print(f"get({key!r}) -> {v!r}")
    except Exception as e:
        print(f"get({key!r}) raised {type(e).__name__}: {e}")

# 3. Структура values геотегов (требует реальный GeoTIFF)
if len(sys.argv) > 1:
    g = TIFF(sys.argv[1])
    for tag in (TIFFTag.ModelPixelScaleTag, TIFFTag.ModelTiePointTag,
                TIFFTag.ModelTransformationTag, TIFFTag.GeoKeyDirectoryTag):
        raw = g.get(tag)
        first = g.get(tag, first=True)
        print(tag.name, "| raw:", repr(raw)[:200], "| first:", repr(first)[:200])
```

- [ ] Запустить: `uv run python C:\Temp\opencode\tiffdata_semantics_check.py <фикстура.tif>` (workdir: репо).
- [ ] Зафиксировать в отчёте: (а) что возвращает `get()` по отсутствующему тегу; (б) бросает ли `TypeError` на `"NoSuchTagXYZ"` и на GPS/EXIF-именах; (в) структура `raw`/`first` для геотегов — плоский список или вложенный; (г) тип ASCII-тега GDALNoData (str или bytes).

### Шаг 2: [core-agent] → `core/georaster/georef.py`, `core/georaster/georaster.py` → переименование + починка семантики
Зависит от Шага 1. Индексацию в пунктах 2.3–2.4 скорректировать по итогам Шага 1 (ожидается плоский список; если вложенный — взять `first=True` и распаковывать датум).

- [ ] **2.1** `georef.py:87` — `def fromTyf(cls, tiff: TIFF):` → `def fromTIFF(cls, tiff: TIFF):`
- [ ] **2.2** `georef.py:127` — удалить строку `# geotags = Tyf.gkd.Gkd(tif)` (блок комментариев про cellAnchor оставить).
- [ ] **2.3** `georef.py:129–135` — `except KeyError` мёртв (tiffdata возвращает `None`). Заменить на:

```python
        # tiffdata returns None for a missing tag instead of raising KeyError
        geotags = tiff.get(TIFFTag.GeoKeyDirectoryTag)
        if geotags is None:
            cellAnchor = 1  # if this key is missing then RasterPixelIsArea is the default
        else:
            # get GTRasterTypeGeoKey value
            cellAnchor: int = int(geotags[geotags.index(1025) + 3])  # http://www.remotesensing.org/geotiff/spec/geotiff2.4.html
```

- [ ] **2.4** `georef.py:96, 101, 103` — для одиночных тегов добавить `first=True` (единая семантика со стр. 89–90):

```python
        transformMatrix = tiff.get(TIFFTag.ModelTransformationTag, first=True)
        ...
        modelTiePoint = tiff.get(TIFFTag.ModelTiePointTag, first=True)
        modelPixelScale = tiff.get(TIFFTag.ModelPixelScaleTag, first=True)
```

Распаковку `(a, b, ... p) = transformMatrix` и индексацию `modelTiePoint[3]`, `modelPixelScale[0]` сохранить (или поправить по результатам Шага 1). Аннотации типов и `# type: ignore` сохранить/актуализировать под новый вызов.
- [ ] **2.5** `georef.py` — docstring стр. 88 уже корректен; TODO-комментарии стр. 93–95 и 141 оставить (вне скоупа).
- [ ] **2.6** `georaster.py:189` — `self.georef = GeoRef.fromTyf(tiff)` → `GeoRef.fromTIFF(tiff)`.
- [ ] **2.7** `georaster.py:183–185` — убрать `assert` (при отсутствии тега `nodata is None`):

```python
        nodata = tiff.get(TIFFTag.GDALNoData, first=True)
        if nodata is not None:
            self.noData = float(nodata)
```

(если Шаг 1 показал bytes — `float(nodata.decode())`).

### Шаг 3: [operators-agent] → `operators/add_camera_exif.py` → починка обработки отсутствующих EXIF-тегов
Зависит от Шага 1, **параллелен Шагу 2** (файлы не пересекаются). Семантику умножения `lat = exif.get("GPSLatitude") * exif.get("GPSLatitudeRef")` сохранить как есть.

- [ ] **3.1** Строки 143–146 — заменить устаревший комментарий про Tyf на:

```python
            #Note : tiffdata get() returns None for a missing tag (it never raises KeyError),
            #and raises TypeError for an unreconcilable tag name,
            #that's why we check for None explicitly instead of try/except KeyError blocks
```

- [ ] **3.2** Строки 148–153 — заменить на:

```python
            lat = exif.get("GPSLatitude")
            latRef = exif.get("GPSLatitudeRef")
            lon = exif.get("GPSLongitude")
            lonRef = exif.get("GPSLongitudeRef")
            if None in (lat, latRef, lon, lonRef):
                self.report({'ERROR'}, "Can't find GPS longitude or latitude.")
                return {'CANCELLED'}
            lat = lat * latRef
            lon = lon * lonRef
```

- [ ] **3.3** Строки 155–159 (`alt`) — заменить на:

```python
            alt = exif.get("GPSAltitude")
            if alt is None:
                alt = 0
```

- [ ] **3.4** Строки 168–171 (`focalLength`) — заменить на:

```python
            focalLength = exif.get("FocalLengthIn35mmFilm")
            if focalLength is None:
                focalLength = 35
```

- [ ] **3.5** Строки 201–204 (`orientation`) — заменить на:

```python
                orientation = exif.get("Orientation")
                cam['orientation'] = orientation if orientation is not None else 1  #no rotation
```

- [ ] **3.6** Не трогать табы в `register()/unregister()` (строки 291–307) и закомментированный блок 188–194.

### Шаг 4: [migrate-agent] → `core/lib/Tyf/` → удаление мёртвого вендорного кода
Зависит от Шагов 2 и 3 (нужны вычищенные упоминания для чистого пре-чека).

- [ ] **4.1** Пре-чек: `rg -n "Tyf" -g '!core/lib/Tyf/**' -g '!.venv/**' -g '!.opencode/**' -g '!docs/**' -g '!AGENTS.md'` → ожидается 0 совпадений (если есть — остановиться, сообщить оркестратору).
- [ ] **4.2** Удалить `core/lib/Tyf/` целиком (включая `__pycache__`). `core/lib/{shapefile*,imghdr,imageio}` не трогать — другие миграции вне скоупа.

### Шаг 5: [docs-review-agent] → `AGENTS.md` → документация + финальное ревью
Зависит от Шага 4.

- [ ] **5.1** `AGENTS.md:16` — `vendored libs (shp, Tyf, imageio)` → `vendored libs (shp, imageio)`.
- [ ] **5.2** Ревью всего диффа: нет остаточных упоминаний Tyf в first-party коде; отступы сохранены; `.opencode/`, `docs/superpowers/2026-07-19-*`, `opencode.jsonc` не изменены; никакой «оптимизации» не внесено.

### Шаг 6: Верификация (финальные ворота, все агенты отчитались)
- [ ] `uv run python -m py_compile core\georaster\georef.py core\georaster\georaster.py operators\add_camera_exif.py` → без ошибок.
- [ ] Повторить пре-чек из Шага 4.1 → 0 совпадений.
- [ ] Повторить Шаг 1 со скриптом (он не зависит от правок — контроль, что библиотека в `.venv` цела).
- [ ] Ручной чек-лист в Blender (перезагрузить аддон): импорт GeoTIFF через georaster-импортёр (геопривязка читается, нет warning'а «Cannot extract georefencing»), оператор Geophotos на геотегированном JPEG (камера создаётся; на JPEG без GPS — корректная ошибка «Can't find GPS longitude or latitude», не краш).

---

## Зависимости и параллелизация

```
Шаг 0 (пре-чек)
   └─> Шаг 1 (верификация tiffdata)
          ├─> Шаг 2 (core: georef.py + georaster.py)  ─┐
          └─> Шаг 3 (operators: add_camera_exif.py)    ─┤ (2 и 3 параллельно)
                                                        ├─> Шаг 4 (удаление core/lib/Tyf)
                                                        │       └─> Шаг 5 (AGENTS.md + ревью)
                                                        │               └─> Шаг 6 (финальная верификация)
```

- **Параллельно:** Шаг 2 ∥ Шаг 3 — разные файлы, разные агенты, общая зависимость только от Шага 1.
- **Последовательно:** 4 → 5 → 6; Шаг 4 нельзя начинать до завершения 2 и 3 (пре-чек по grep даст ложный позитив из-за `fromTyf`/комментариев).

## Grep-запросы (уже выполнены планировщиком, результаты в шапке)

1. `Tyf` по всему репо → только комментарии, имя метода `fromTyf`, вендорный lib, docs, `.opencode` (импортов нет).
2. `(from|import)\s+Tyf` → 0 совпадений.
3. `tiffdata` → `add_camera_exif.py:38`, `georef.py:6`, `georaster.py:25`, deps-файлы, `.venv`.
4. `TIFF` в `core/` → только `georef.py`, `georaster.py` (tiffdata), `bigtiffwriter.py`/`reproj.py` (GDAL — вне скоупа), вендорные либы.
5. `def get` в `.venv/.../tiffdata/__init__.py` → сигнатура `get(key, default=None, ifd=0, first=False)`; возврат `tag.values[0]` при `first=True`, иначе `tag.values`; при отсутствии тега — `return default` (None); неопознанная строка → `TypeError`.
6. `TIFFTag.*` в `.venv/.../tifftag.py` → `ModelPixelScaleTag`, `ModelTiePointTag`, `ModelTransformationTag`, `GeoKeyDirectoryTag`, `GDALNoData`, `ImageWidth` существуют.

**Осталось невыясненным статически (закрывается Шагом 1):** структура `tag.values` для геотегов (плоский/вложенный), факт `TypeError` для GPS/EXIF-имён через `TIFFTag.reconcile`, тип ASCII-значения GDALNoData (str/bytes).
