# v4.2.1 change notes

- Processing Scope now auto-fills the canonical PostgreSQL database name:
  - `21MM` -> `rag_21mm`
  - `24MM` -> `rag_24mm`
  - `Common` -> `rag`
- Scope selection overwrites stale database mappings from older user config files.
- The Database field remains editable after auto-fill for deliberate one-off/custom use.
- Existing behavior that clears pending input files when switching scope is unchanged.
- No PostgreSQL schema change is required.
