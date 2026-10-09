"""OS abstraction package (ADR-0003).

`base.py` defines the common interface; `macos.py`, `windows.py`,
`linux.py` provide per-platform implementations; `registry.py` selects
the right one at runtime and enables tests to inject fakes.
"""