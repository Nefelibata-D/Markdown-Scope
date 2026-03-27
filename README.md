# markdown-scope

`markdown-scope` is a CLI for building a structured Markdown index and reading only the parts you need.

- Project name: `markdown-scope`
- CLI name: `md-scope`

## Install

Use `uv` (recommended):

```bash
uv sync
uv run md-scope --help
```

Use `pip`:

```bash
pip install .
md-scope --help
```

## What It Generates

For one root directory, `build`/`update` writes:

- Public index: `ROOT/.mdx-index.json`
- Lock index: `ROOT/.mdx-index.lock.json`

Public index is for reading/searching.  
Lock index keeps internal metadata for `update` reuse.

## Commands

### `build`

Build index from scratch for a root directory.

Common options:

- `--root`: Markdown root directory
- `--index`: custom public index path (default `ROOT/.mdx-index.json`)
- `--overwrite`: overwrite existing index
- `--include`: file glob patterns (repeatable)
- `--config`: TOML config path
- `--format`: output format (`json|text|markdown`, mostly `json`)

Summary-related options:

- `--provider`
- `--api-base`
- `--api-key`
- `--model`
- `--system-prompt`
- `--user-prompt`
- `--summary-root-level`
- `--summary-exclude-levels`
- `--include-excluded-ancestors-as-context`

Example:

```bash
uv run md-scope build --root ./examples --config ./md-scope.toml
```

### `update`

Incremental rebuild using lock metadata. Unchanged sections reuse id/summary when possible.

Common options are similar to `build`:

- `--root`
- `--index`
- `--include`
- `--config`
- `--format`
- all summary-related options

Example:

```bash
uv run md-scope update --root ./examples --config ./md-scope.toml
```

### `outline`

Read index outline (tree/catalog view).  
Default target behavior: if `SKILL.md` exists, it is preferred when no target is provided.

Options:

- `--root`
- `--index`
- `--target`: file or directory scope
- `--format`: `json|text|markdown`
- `--full`: only for JSON, include `line_count/level/start/end`

Examples:

```bash
uv run md-scope outline --root ./examples --format json
uv run md-scope outline --root ./examples --target references --format text
uv run md-scope outline --root ./examples --format json --full
```

### `catalog`

Alias of `outline` (same behavior and parameters).

### `search`

Search sections in index by title/path/summary.

Options:

- `--root`
- `--index`
- `--query` (required)
- `--field`: `all|title|path|summary`
- `--target`: limit to file/directory scope
- `--format`
- `--full`: only for JSON, include range metadata

Example:

```bash
uv run md-scope search --root ./examples --query install --field all
```

### `read-lines`

Read raw Markdown by 1-based line range.

Options:

- `--root`
- `--file` (required): relative markdown path under root
- `--start` (required)
- `--end` (required)
- `--max-lines`
- `--format`

Example:

```bash
uv run md-scope read-lines --root ./examples --file SKILL.md --start 1 --end 40 --max-lines 60
```

### `read-section`

Read section(s) by id from index.

Options:

- `--root`
- `--index`
- `--id` (repeatable)
- `--max-lines`
- `--mode`: `simple|contextual`
- `--format`

Modes:

- `simple`: direct section-range read (`id` maps to its indexed `start/end`)
- `contextual`: path-aware reconstruction for AI
  - returns ancestor heading + intro context
  - returns target full subtree
  - excludes unrelated siblings
  - deduplicates ancestor/descendant target overlap

Return shape:

- Single `--id`: returns one object
- Multiple `--id` in `simple`: returns `{ "results": [...], "errors": [...] }`
- Multiple `--id` in `contextual`: returns grouped contextual payload (`single-file` or `files` array)

Examples:

```bash
uv run md-scope read-section --root ./examples --id section-a
uv run md-scope read-section --root ./examples --id section-a --id section-b --mode simple --format json
uv run md-scope read-section --root ./examples --id section-a --id section-b --mode contextual --format text
```

### `md-files`

List Markdown files under root (or subdirectory), useful for agent/tool discovery.

Options:

- `--root`
- `--target`: optional subdirectory
- `--format`

Example:

```bash
uv run md-scope md-files --root ./examples --format json
uv run md-scope md-files --root ./examples --target references --format markdown
```

### Hidden Compatibility Alias

- `view` is kept as hidden alias for `outline`.

## Config (`md-scope.toml`)

Use one `[global]` section for reusable defaults.
CLI arguments override config values.

Example:

```toml
[global]
root = "./examples"
index = "./examples/.mdx-index.json"
include = ["*.md", "**/*.md"]
overwrite = true

provider = "openai-compatible"
api_base = "https://api.openai.com/v1"
api_key = "YOUR_KEY"
model = "gpt-5-mini"
system_prompt = "You are a concise technical summarizer."
user_prompt = "Summarize in Chinese:\n{content}"

summary_root_level = 2
summary_exclude_levels = [1]
include_excluded_ancestors_as_context = true

format = "json"
max_lines = 200
```

## Index Shape (Public)

```json
{
  "files": [
    {
      "file-name": "SKILL.md",
      "line_count": 100,
      "sections": [
        {
          "id": "intro-ab12",
          "title": "Intro",
          "level": 2,
          "start": 10,
          "end": 30,
          "summary": "..."
        }
      ]
    }
  ]
}
```

## Development

Run tests only in project venv:

```bash
uv run pytest
```
