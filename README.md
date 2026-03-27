# markdown-scope

`markdown-scope` is a Python CLI for structured indexing and selective reading of Markdown trees.  
It is designed for AI/agent workflows to avoid loading full large `.md` files when only specific sections are needed.

## Features

- Build one root-level JSON index for all Markdown files under a directory
- Build one public index (`.mdx-index.json`) plus one lock index (`.mdx-index.lock.json`)
- Preserve heading hierarchy (`#` to `######`) as a section tree
- Public JSON keeps only core fields: `file-name`, `line_count`, `id`, `title`, `level`, `start`, `end`, `summary`
- Update index with section summary/id reuse when content is unchanged
- View/search index by file or directory scope
- Read raw Markdown by line range or by section id
- Export index as Markdown catalog (not original content)
- Build/Update progress uses hierarchical logs (file -> top-level section) for long-running jobs

## Install

### Using uv (recommended)

```bash
uv sync
```

Run CLI from the uv environment:

```bash
uv run md-scope --help
```

### Using pip

```bash
pip install .
md-scope --help
```

## Quick Start

Build index (default index file: `ROOT/.mdx-index.json`):

```bash
uv run md-scope build --root ./examples --provider openai-compatible --api-base ... --api-key ... --model ... --system-prompt "..." --user-prompt "..."
```

Using config file:

```bash
uv run md-scope build --config ./md-scope.toml
```

Update existing index:

```bash
uv run md-scope update --root ./examples --provider openai-compatible --api-base ... --api-key ... --model ... --system-prompt "..." --user-prompt "..."
uv run md-scope update --config ./md-scope.toml
```

View index (default prefers `SKILL.md` if exists):

```bash
uv run md-scope view --root ./examples --format json
uv run md-scope view --root ./examples --format json --full
uv run md-scope view --root ./examples --target reference --format text
uv run md-scope view --root ./examples --target reference --format markdown
uv run md-scope view --config ./md-scope.toml
```

Search:

```bash
uv run md-scope search --root ./examples --query install --field all
uv run md-scope search --root ./examples --query install --field all --full
uv run md-scope search --config ./md-scope.toml
```

Read by lines:

```bash
uv run md-scope read-lines --root ./examples --file SKILL.md --start 1 --end 20 --max-lines 50
uv run md-scope read-lines --config ./md-scope.toml
```

Read by section id:

```bash
uv run md-scope read-section --root ./examples --id a1b2c3d4e5f60708 --max-lines 200
uv run md-scope read-section --config ./md-scope.toml --id a1b2c3d4e5f60708
```

Export Markdown catalog:

```bash
uv run md-scope export-md --root ./examples --output ./examples/catalog.md
uv run md-scope export-md --config ./md-scope.toml
```

## Config File

Project root includes a sample config: `md-scope.toml`.

- Use `--config <path>` with any command.
- Config is global defaults only (for example `root/index/provider/include/system_prompt/user_prompt`).
- Dynamic runtime params still come from CLI (for example `search --query`, `read-lines --file --start --end`, `read-section --id`).
- CLI args override config values.
- Config uses one `[global]` section (no per-command sections).

Example shape:

```toml
[global]
root = "./examples"
index = "./examples/.mdx-index.json"
include = ["*.md", "**/*.md"]
summary_root_level = 2
summary_exclude_levels = [1]
include_excluded_ancestors_as_context = true
provider = "openai-compatible"
format = "json"
system_prompt = "You are a concise technical summarizer."
user_prompt = "Summarize in Chinese:\n{content}"

field = "all"
```

`user_prompt` supports placeholders:

- `{title}`
- `{top_title}`
- `{file_path}`
- `{content}`
- `{TOP_LEVEL_TITLE}`
- `{FILE_PATH}`
- `{MARKDOWN_SUBTREE}`
- `{SECTION_ID_MAP_TEXT}`

## Summary Provider

`summary` is generated through a provider interface:

- `openai-compatible`: remote API via `/chat/completions` with `response_format=json_schema`
- New/changed sections are summarized in batch per top-level section with `response_format=json_schema`.
- Model output is expected as JSON object keyed by section `id`.
- If required AI config is missing (`api_base/api_key/model/system_prompt/user_prompt`), summary is skipped and section summary is filled with `AI Summary can't be generated: ...`.

Example:

```bash
uv run md-scope build \
  --root ./examples \
  --provider openai-compatible \
  --api-base https://api.openai.com/v1 \
  --api-key $OPENAI_API_KEY \
  --model gpt-4.1-mini
```

## Public Index JSON Shape (simplified)

```json
{
  "files": [
    {
      "file-name": "SKILL.md",
      "line_count": 12,
      "sections": [
        {
          "id": "skill-overview",
          "title": "Skill Overview",
          "level": 1,
          "start": 1,
          "end": 12,
          "summary": "...",
          "children": []
        }
      ]
    }
  ]
}
```

Lock file (`.mdx-index.lock.json`) stores hashes/paths/internal metadata for `update` reuse logic.

Full sample: `examples/sample-index.json`

## CLI Commands

- `build`
- `update`
- `view`
- `search`
- `read-lines`
- `read-section`
- `export-md`

Run detailed help:

```bash
uv run md-scope <command> --help
```

## Error Handling

The CLI provides explicit errors for:

- Missing root/index/path
- Invalid line ranges (`start <= 0`, `start > end`, out-of-range start)
- Unknown section id
- Target outside index scope
- Markdown decode errors
- Corrupted index file
- Summary provider misconfiguration/failure

## Development

Install development dependencies:

```bash
uv sync --dev
```

Tests (optional):

```bash
uv run pytest
```
