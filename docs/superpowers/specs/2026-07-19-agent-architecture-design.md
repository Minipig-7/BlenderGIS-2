# BlenderGIS Agent Architecture

**Date**: 2026-07-19
**Project**: BlenderGIS v2.2.14
**Purpose**: Define a set of specialized opencode subagents for efficient work on the BlenderGIS codebase — new features, bugfixes, optimization, migrations, and documentation.

---

## Design Summary

A three-layer agent architecture:

1. **Planner** — writes implementation plans for complex tasks (powerful model, rare use)
2. **Orchestrator** — the human + opencode routing tasks to subagents
3. **Subagents** — lightweight specialists, each owning a slice of the codebase

---

## File Organization

All agent definitions live in `.opencode/agents/*.md`:

```
.opencode/agents/
  planner.md
  core-agent.md
  operators-agent.md
  geo-ui-agent.md
  migrate-agent.md
  optimize-agent.md
  docs-review-agent.md
```

Each file uses YAML frontmatter + markdown body:

```yaml
---
name: agent-name
model: cheap|medium|powerful
files: [list of file paths]
readonly: false
allowed_tools: [read, edit, grep, glob, bash]
blocked_tools: [websearch, webfetch]
---
```

---

## Agent Definitions

### 1. Planner

| Field | Value |
|-------|-------|
| Model | powerful (Sonnet / DeepSeek V4) |
| Access | all files (read-only) |
| Trigger | tasks with 3+ steps or 2+ domains |

Reads AGENTS.md + project structure + grep results. Outputs a markdown plan where each step is:
`[agent] → [files] → [what to do]`

Includes dependency ordering and what can be parallelized.

---

### 2. Orchestrator (the human + opencode)

- Receives a task
- If complex → invokes Planner
- Distributes work to subagents via `task` (parallel where possible)
- After execution → invokes Docs-Review Agent
- Presents result to human for sign-off
- Uses `question` tool for clarification, never makes important decisions silently

---

### 3. Core Agent

| Field | Value |
|-------|-------|
| Model | cheap (Haiku, GPT-4o-mini, DeepSeek Coder V3) |
| Files | `core/proj/`, `core/georaster/`, `core/basemaps/`, `core/maths/`, `core/utils/` |
| Blocked | `core/lib/` (vendored) |

Rules:
- Tabs for indentation
- No comments (docs-review handles that)
- Relative imports (`from .proj import ...`)
- Prefer numpy vectorization over loops
- Preserve `if HAS_GDAL:` / `if HAS_PYPROJ:` dual paths

---

### 4. Operators Agent

| Field | Value |
|-------|-------|
| Model | cheap |
| Files | `operators/*.py` (except `delaunay_voronoi.py`) |

Rules:
- New operator → create file, add feature flag in `__init__.py`, add import + register/unregister, update `operators/__init__.py`
- Tabs
- No comments
- Use utilities from `operators/utils/`, don't duplicate
- Follow patterns of neighboring operators

---

### 5. Geo-UI Agent

| Field | Value |
|-------|-------|
| Model | cheap |
| Files | `geoscene.py`, `prefs.py`, `__init__.py` |

Critical rules:
- `geoscene.py` = spaces; `prefs.py` / `__init__.py` = tabs. NEVER mix.
- `prefs.py`: `get_transform`/`set_transform` for Blender 5.x, else `get`/`set`
- `__init__.py`: feature flags at lines ~30-43; import / register / unregister under matching flag
- Update `operators/__init__.py.__all__` when adding operators

---

### 6. Migrate Agent

| Field | Value |
|-------|-------|
| Model | medium |
| Files | all first-party code |
| Blocked | `core/lib/`, `operators/lib/` (vendored) |

Process:
1. Grep all imports and usages of old library
2. Create replacement plan
3. Replace one file at a time, preserving semantics
4. If API doesn't match 1:1 → create adapter/wrapper

Known migrations:
- Tyf → tiffdata: `Tyf.TiffFile` → `tiffdata.TiffFile`
- pyshp → geopandas: `shapefile.Reader` → `geopandas.read_file()`
- imageio → PIL: `imageio.imread()` → `Image.open()`

---

### 7. Optimize Agent

| Field | Value |
|-------|-------|
| Model | medium |
| Access | read-only grep on all, write only to specified files |

Targets:
- `for` loops over numpy arrays → vectorized operations
- `list.append` in loops → list comprehension or numpy
- Repeated computation → caching
- Deep recursion → iterative approach
- `.copy()` on large arrays → view or in-place
- Per-point `reprojPt` calls → bulk `reprojPts`

Rules:
- No vendored code optimization
- Read full file before editing
- If change > 100 lines → show diff to human

---

### 8. Docs-Review Agent

| Field | Value |
|-------|-------|
| Model | cheap |
| Files | all |

#### Documentation Mode
- Doxygen `/** */` blocks on public functions/classes > 15 lines or with non-trivial logic
- Inline comments only for: magic constants, non-obvious formulas, Blender API workarounds, complex geometry
- Language: English for code, Russian for AGENTS.md (matching current convention)

#### Review Mode (before task completion)
Check:
1. No leftover TODO/FIXME/HACK
2. New operators registered in `__init__.py` and `operators/__init__.py`
3. Imports are valid
4. Feature flags added for new operators
5. Indentation matches file convention
6. No duplicate imports

---

## Task Flow

```
1. Task arrives
2. If complex → invoke Planner agent
3. Planner returns implementation plan
4. Orchestrator dispatches subagents (parallel where possible)
5. Subagents execute their steps
6. Docs-Review Agent runs review
7. Orchestrator presents result to human for sign-off
```

---

## Interaction Rules

- **Parallelism**: agents without shared file dependencies run in parallel
- **Read-before-write**: every agent reads a file before editing it
- **Minimal context**: agents use grep/glob instead of reading entire files; planner only gets AGENTS.md + structure, not full codebase
- **Human escalation**: orchestrator uses `question` tool when unclear
