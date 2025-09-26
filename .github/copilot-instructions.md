# Copilot Instructions (Submodule: sck-core-organization)

- Tech: Python package.
- Precedence: Local first; root `../../.github/...` next.
- Conventions: Follow `../sck-core-ui/docs/backend-code-style.md` where relevant.

## Google Docstring Requirements
**MANDATORY**: All docstrings must use Google-style format for Sphinx documentation generation:
- Use Google-style docstrings with proper Args/Returns/Example sections
- Napoleon extension will convert Google format to RST for Sphinx processing
- Avoid direct RST syntax (`::`, `:param:`, etc.) in docstrings - use Google format instead
- Example sections should use `>>>` for doctests or simple code examples
- This ensures proper IDE interpretation while maintaining clean Sphinx documentation

## Contradiction Detection
- Check against backend code style and root precedence.
- If conflict, warn + options + example.
- Example: "Storing PII in logs conflicts with security guidance; redact and use core_logging helpers."

## Standalone clone note
If cloned standalone, see:
- UI/backend conventions: https://github.com/eitssg/simple-cloud-kit/tree/develop/sck-core-ui/docs
- Root Copilot guidance: https://github.com/eitssg/simple-cloud-kit/blob/develop/.github/copilot-instructions.md
 
