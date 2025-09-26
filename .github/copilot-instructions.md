# Copilot Instructions (Submodule: sck-core-organization)

- Tech: Python package.
- Precedence: Local first; root `../../.github/...` next.
- Conventions: Follow `../sck-core-ui/docs/backend-code-style.md` where relevant.

## RST Documentation Requirements
**MANDATORY**: All docstrings must be RST-compatible for Sphinx documentation generation:
- Use proper RST syntax: `::` for code blocks (not markdown triple backticks)
- Code blocks must be indented 4+ spaces relative to preceding text
- Add blank line after `::` before code content
- Bullet lists must end with blank line before continuing text
- Use RST field lists for parameters: `:param name: description`
- Use RST directives: `.. note::`, `.. warning::`, etc.
- Test docstrings with Sphinx build - code is source of truth, not docstrings

## Contradiction Detection
- Check against backend code style and root precedence.
- If conflict, warn + options + example.
- Example: "Storing PII in logs conflicts with security guidance; redact and use core_logging helpers."

## Standalone clone note
If cloned standalone, see:
- UI/backend conventions: https://github.com/eitssg/simple-cloud-kit/tree/develop/sck-core-ui/docs
- Root Copilot guidance: https://github.com/eitssg/simple-cloud-kit/blob/develop/.github/copilot-instructions.md
 
