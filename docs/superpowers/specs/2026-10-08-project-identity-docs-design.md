# Project identity & documentation rewrite — design

**Date:** 2026-10-08
**Scope:** Documentation and metadata only. No functional code changes.

## Problem

The current `README.md` is a verbatim copy of the upstream `domlysz/BlenderGIS`
README. It presents this repository as the original project, points at the
upstream wiki, and says nothing about the fact that this is an independently
developed clone. Anyone landing here concludes they are looking at upstream.

The same mismatch exists in:

- `pyproject.toml` — placeholder `description = "Add your description here"`, and
  a `version = "0.1.0"` that has nothing to do with the add-on version.
- `__init__.py` `bl_info` — `wiki_url` / `tracker_url` point at upstream.
- `AGENTS.md` — describes the project as "BlenderGIS, v2.2.14" with no fork
  context, so an agent reading it has no idea this is a derivative work.
- No `LICENSE` or `NOTICE` file at all, despite `bl_info['license'] = 'GPL'`
  and the code being a GPL derivative. GPL requires that the license and
  attribution travel with the source.

## Goals

1. Make the fork's identity unambiguous, with a link to the original repository
   at the very top of the README.
2. State the project's goals: fix and improve existing functionality, optimize
   performance, add new functionality, refactor for readability and modern
   Python standards and best practices.
3. Record that development is AI-tool-assisted.
4. Keep the genuinely useful upstream content (feature overview, install notes)
   rather than discarding it.
5. Bring metadata and `AGENTS.md` in line with the new README.
6. Satisfy GPL attribution obligations.

## Non-goals

- No roadmap of concrete planned features. Goals are stated; concrete near-term
  work items are not enumerated in the README.
- No renames. The product keeps the name "BlenderGIS" with an explicit
  "unofficial clone" qualifier.
- No new repository URLs. `wiki_url` / `tracker_url` are removed from
  `bl_info` rather than repointed, because no fork repository exists yet.
- No code, dependency, or architectural changes.

## Decisions

### Naming

Keep `BlenderGIS` as the product name, always paired with an explicit
"unofficial clone / community fork of domlysz/BlenderGIS" qualifier. Renaming
would break the `bl_info` name users see in Blender's add-on list and would
add no clarity that the qualifier does not already provide.

### README structure

Full rewrite, English body with a Russian summary section at the end. Sections:

1. **Fork notice** — first thing in the document. States this is not the original
   project, links to `https://github.com/domlysz/BlenderGIS`, states it is
   developed separately, and notes AI-tool assistance.
2. **What this project is** — a Blender add-on for geospatial data, forked from
   upstream at v2.2.14.
3. **Goals** — the four declared goals (improve functionality, optimize, add
   features, refactor) plus the AI-assisted development note.
4. **Inherited functionality** — the upstream feature overview, preserved:
   GIS data import, web geodata, terrain building, georeferencing, terrain
   analysis, geotagged photos, raster rendering. Minimum Blender version and
   the OpenTopography API key note are kept here.
5. **Documentation** — points at the upstream wiki for user-facing guides,
   clearly labelled as upstream documentation.
6. **License and attribution** — GPL-3.0, credits domlysz, links `LICENSE` and
   `NOTICE.md`.
7. **Краткое резюме (Russian)** — condensed Russian version of points 1–6.

Approaches considered and rejected:

- *Minimal delta* (prepend a banner, keep the rest as-is): does not fix the
  upstream wiki links or the implicit "this is upstream" framing deeper in the
  document.
- *Split into README + `docs/`*: unnecessary fragmentation for a project with no
  docs site.

### `pyproject.toml`

- `description` → real one-liner describing the add-on as an unofficial clone.
- Add `readme = "README.md"` so the package metadata carries the fork notice.
- `version = "0.1.0"` is left alone. It is the version of the dev environment,
  not the add-on; the add-on version lives in `bl_info`. Removing it would break
  `uv`. A comment records the distinction.
- Dependency list is untouched.

### `__init__.py` `bl_info`

- `wiki_url` and `tracker_url` removed.
- `author` stays `domlysz` — GPL requires the original author be credited.
  Add-on attribution is not ours to reassign.
- `name`, `version`, `blender`, `license`, `location`, `category` unchanged.
- The add-on's visible description string is left alone: changing it is a user
  facing behaviour change, out of scope for a docs pass.

### LICENSE / NOTICE

- `LICENSE` holds the full GNU GPL v3 text (fetched from gnu.org, not
  hand-written).
- `NOTICE.md` holds the attribution notice: original work by domlysz, this
  derivative work, GPL-3.0 obligations, upstream link.
- This is the "full text" option over a stub, because a stub would not actually
  convey the license.

### AGENTS.md

The operational content is accurate and stays as-is: feature flags, directory
boundaries, dependencies, commands, quirks, secrets handling. Only these change:

- "What this is" → describes the fork, adds the upstream link, states the goals
  so an agent knows what direction changes should move in.
- A short "Project goals" section, mirroring the README so the two do not drift.
- A "License" line pointing at `LICENSE` and `NOTICE.md`, so an agent does not
  strip attribution headers during refactors.
- Docs to update: note that `README.md` and this file must be kept in sync.

## Verification

- No build or test suite exists in this project (`AGENTS.md` records this), so
  verification is manual: read each changed file back, confirm the upstream URL
  is correct and live, confirm no remaining references to upstream as "the"
  project, confirm `bl_info` still parses as a dict literal.
- `uv sync` is not re-run; no dependency changed.