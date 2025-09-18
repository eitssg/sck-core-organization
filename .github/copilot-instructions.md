# Copilot Instructions (Submodule: sck-core-organization)

- Tech: Python package.
- Precedence: Local first; root `../../.github/...` next.
- Conventions: Follow `../sck-core-ui/docs/backend-code-style.md` where relevant.

## Contradiction Detection
- Check against backend code style and root precedence.
- If conflict, warn + options + example.
- Example: "Storing PII in logs conflicts with security guidance; redact and use core_logging helpers."

## Standalone clone note
If cloned standalone, see:
- UI/backend conventions: https://github.com/eitssg/simple-cloud-kit/tree/develop/sck-core-ui/docs
- Root Copilot guidance: https://github.com/eitssg/simple-cloud-kit/blob/develop/.github/copilot-instructions.md
 
