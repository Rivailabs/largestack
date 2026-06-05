# Internal Test & Soak Logs

This directory holds the maintainer's own local test, soak, and smoke-run logs.
They are development notes — **not** independent validation, audits, or
certifications. See `docs/known-limitations.md` for what is actually proven.

It is a curated index, not a dumping ground for every generated project, raw
log, cache file, or scratch run.

## Public Repo Policy

Keep these in git:

- top-level `*_LATEST.md` evidence summaries,
- `SUMMARY.md` / `FINAL*_SUMMARY.md` files for named validation runs,
- one final public validation summary for each release,
- short human-written notes that explain how to reproduce the run.

Do not keep these in git:

- generated project source trees,
- raw provider JSON outputs,
- full pytest/security/Docker logs,
- scan caches,
- temporary scratch directories.

Put bulky raw artifacts in GitHub Release assets, CI artifacts, object storage,
or a private evidence archive, then link them from the curated summaries.

## Current Public Shape

This checkout keeps only curated evidence summaries under git tracking. Raw
artifacts may still exist locally in ignored directories, but they should be
published as CI artifacts or release attachments, not as public repo files.

Recommended public release shape:

```text
release_evidence/
  README.md
  FINAL_PUBLIC_VALIDATION_<version>.md
  DEEPSEEK_BUILD_PROJECTS_LATEST.md
  REAL_AUTONOMOUS_100_LATEST.md
  REAL_PROJECTS_CAPSTONE_LATEST.md
  JARVIS_CAPSTONE_LATEST.md
  soak_24h/SUMMARY.md
```
