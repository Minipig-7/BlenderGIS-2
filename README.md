# BlenderGIS

> **This is not the original BlenderGIS project.**
>
> This repository is an **unofficial clone** of
> [domlysz/BlenderGIS](https://github.com/domlysz/BlenderGIS), developed
> independently and separately from the original. The original project and its
> author are not affiliated with, nor do they endorse, this fork.
>
> All credit for the original work goes to [domlysz](https://github.com/domlysz).

---

BlenderGIS is a Blender add-on for working with geospatial data inside Blender:
importing GIS files, building terrain meshes, fetching live web map data, and
managing scene georeferencing.

This fork starts from upstream **v2.2.14** and targets **Blender 5.2+**.

## Goals of this project

This is an active fork with four standing goals:

1. **Improve existing functionality** — fix bugs, correct incorrect behaviour, and
   make the existing features work the way they are documented to work.
2. **Optimize performance** — profile and speed up the heavy paths: raster and
   vector parsing, triangulation, DEM handling, and large-dataset imports.
3. **Add new functionality** — grow the feature set beyond what upstream offers.
4. **Refactor the codebase** — restructure for readability and alignment with
   modern Python standards and best practices, without changing user-facing
   behaviour.

Development is assisted by AI coding tools. Changes are reviewed and tested by
a human maintainer before they land.

## Inherited functionality

The following capabilities come from upstream and continue to work. This list
describes what the add-on does, not the current state of each feature — some of
it is known to need the improvements listed under [Goals](#goals-of-this-project).

**GIS data import** — import the most common GIS formats into Blender:
Shapefile vector data, raster images, GeoTIFF DEMs, and OpenStreetMap XML.

**Web geodata** — display dynamic web maps inside the 3D viewport, request
OpenStreetMap data (buildings, roads, and more), and fetch true elevation data
from NASA's SRTM mission.

**Terrain building** — build a terrain mesh from geographic data. For example:
import vector contour lines, create faces by triangulation, and apply a
topographic raster texture.

![terrain from contours](https://raw.githubusercontent.com/wiki/domlysz/blenderGIS/Blender28x/gif/bgis_demo_delaunay.gif)

![grabbing web data](https://raw.githubusercontent.com/wiki/domlysz/blenderGIS/Blender28x/gif/bgis_demo_webdata.gif)

**And more** — manage a scene's georeferencing information, compute a terrain
mesh via Delaunay triangulation, drop objects onto a terrain mesh, perform
terrain analysis with shader nodes, create cameras from geotagged photos, and
set up a camera to render a new georeferenced raster.

## Requirements

- **Blender 5.2 or newer.** The add-on refuses to load on older versions.
- **OpenTopography API key** — required since 2022 for the OpenTopography web
  service. Register at [opentopography.org](https://opentopography.org) and
  request a key. The service is still free.

## Documentation

End-user documentation — quick start guides, FAQ, and the workflow flowchart —
lives in the **upstream** wiki:

- [Wiki](https://github.com/domlysz/BlenderGIS/wiki/Home)
- [FAQ](https://github.com/domlysz/BlenderGIS/wiki/FAQ)
- [Quick start guide](https://github.com/domlysz/BlenderGIS/wiki/Quick-start)
- [Flowchart](https://raw.githubusercontent.com/wiki/domlysz/blenderGIS/flowchart.jpg)

Note that the upstream wiki documents upstream's behaviour. Where this fork has
changed something, the wiki may be out of date.

## License and attribution

This project is licensed under the **GNU General Public License v3.0** — see
[LICENSE](LICENSE).

BlenderGIS was originally created by **domlysz** and is distributed under the
GPL. This repository is a derivative work and is distributed under the same
license, as the GPL requires. Original copyright and attribution are preserved;
see [NOTICE.md](NOTICE.md) for the full attribution notice.

---

## Краткое резюме

**Это не оригинальный проект BlenderGIS.** Данный репозиторий —
неофициальный клон [domlysz/BlenderGIS](https://github.com/domlysz/BlenderGIS),
который развивается отдельно и независимо от оригинала. Автор оригинального
проекта не связан с этим форком и не поддерживает его. Все заслуги в
создании оригинала принадлежат [domlysz](https://github.com/domlysz).

Форк основан на upstream версии **2.2.14** и ориентирован на **Blender 5.2+**.

### Цели проекта

1. **Улучшение существующего функционала** — исправление ошибок и приведение
   поведения к тому, как оно задокументировано.
2. **Оптимизация производительности** — профилирование и ускорение тяжёлых
   участков: разбор растровых и векторных данных, триангуляция, работа с DEM,
   импорт больших наборов данных.
3. **Добавление нового функционала** — расширение возможностей за пределы того,
   что предлагает upstream.
4. **Рефакторинг кода** — перестройка кода для читаемости и соответствия
   современным стандартам и лучшим практикам Python без изменения
   пользовательского поведения.

Разработка ведётся с помощью ИИ-инструментов. Изменения проверяются и
тестируются человеком перед включением в проект.

### Унаследованный функционал

Возможности, полученные от upstream и продолжающие работать: импорт GIS-данных
(Shapefile, растровые изображения, GeoTIFF DEM, OpenStreetMap XML); получение
геоданных из интернета (динамические веб-карты в 3D-виде, запросы к OpenStreetMap,
реальные данные высот NASA SRTM); построение рельефа (например, триангуляция
контурных линий с наложением топографического растра); геореференсирование
сцены, анализ рельефа шейдерными узлами, камеры из геотегированных фотографий
и рендеринг нового геореференсированного растра.

### Требования

- **Blender 5.2 или новее.**
- **API-ключ OpenTopography** — обязателен с 2022 года. Зарегистрируйтесь на
  [opentopography.org](https://opentopography.org) и запросите ключ. Сервис
  остаётся бесплатным.

### Документация

Руководства пользователя, FAQ и блок-схема работы находятся в **вики upstream**:
[Wiki](https://github.com/domlysz/BlenderGIS/wiki/Home) ·
[FAQ](https://github.com/domlysz/BlenderGIS/wiki/FAQ) ·
[Quick start](https://github.com/domlysz/BlenderGIS/wiki/Quick-start).
Учтите, что вики описывает поведение оригинала и может быть неактуально там,
где этот форк вносит изменения.

### Лицензия и авторство

Проект распространяется по лицензии **GNU General Public License v3.0** —
см. [LICENSE](LICENSE). BlenderGIS создан **domlysz** и также распространяется
по GPL. Этот репозиторий является производной работой и распространяется под
той же лицензией, как того требует GPL. Авторские права и авторство сохранены —
полное уведомление см. в [NOTICE.md](NOTICE.md).