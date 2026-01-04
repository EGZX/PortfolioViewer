---
trigger: always_on
globs: "*.py,*.js,*.ts,*.tsx,*.jsx,*.html,*.css,*.go,*.rs,*.java"
---

# Commenting Standards

1.  **Current State Only**: Comments must describe the *current* logic. NEVER reference past versions, "bug fixes", user requests, or "Old code".
2.  **The "Why", not the "What"**: Code should be self-explanatory. Use comments to explain the *intent* or specific business logic complexity, not strictly what the line of code is doing.
3.  **Docstrings**: All public modules, classes, and functions must have descriptive docstrings (e.g., Google Style or standard format) defining inputs, outputs, and side effects.
4.  **No Vanity**: Do not include author names or dates in comments. Version control handles history.
