# Releasing

Maintainer guide. Every fix or feature ends with a version bump and a publish to PyPI.
This file is the checklist for that, and it exists because the steps the tooling does
*not* cover are the ones that get forgotten.

## Choosing the number

Semantic versioning against the **public API** — `Subject`, the container, handler
registration, storage factories, the CloudEvents transports.

| Change | Bump |
|---|---|
| Bug fix, no new API surface | patch — `3.2.1` → `3.2.2` |
| New parameter, method, or backend, backward compatible | minor — `3.2.2` → `3.3.0` |
| Removed or repurposed public API, changed default behavior | major |

Adding an optional parameter that defaults to today's behavior is a **patch** when it
fixes a defect, a **minor** when it adds capability. When in doubt prefer the larger
bump: an unused minor costs nothing, a breaking patch costs a downstream incident.

## Checklist

Steps 1–5 happen on the feature branch, before the closing commit.

1. **Tests pass** — `pytest tests/`. If some fail, establish whether they already failed
   on `main` before treating the release as blocked; don't assume either way.
2. **`pyproject.toml`** — bump `version`.
3. **`uv.lock`** — the lock is committed and records `krules-framework` itself, so it
   must be refreshed (`uv lock`) or it ships pinned to the previous version.
4. **`CHANGELOG.md`** — add an entry under a new `## [x.y.z] - YYYY-MM-DD` heading.
   Describe **observable behavior**, not the diff: what a user of the framework can now
   do, or what silently misbehaved before. Every entry here is also a candidate change
   for the skill (step 5).
5. **Documentation and skill** — update `docs/` for anything whose contract moved, then
   apply the co-evolution rule in [CLAUDE.md](CLAUDE.md): if the release changes what the
   `krules-python` skill asserts, update the skill in the same activity and set its
   `Framework Version` in `SKILL.md` to the number being released. Commit **and push**
   the skill repository *before* moving the submodule pointer here, or the pointer will
   reference an unreachable commit.
6. **Merge to `main` and push.**
7. **Publish** from a clean `main` — see below. Then confirm the version is live on PyPI
   and that `git tag` shows `vx.y.z`.

## Publishing

`tasks.py` provides an [invoke](https://www.pyinvoke.org/) pipeline. `inv release` chains
`check_git_status` → `update_and_tag` → `build` → `publish`, which:

- refuses to run on a dirty tree, off `main`, or behind `origin/main`;
- bumps `version` in `pyproject.toml` and commits it;
- creates and pushes the `vx.y.z` tag;
- builds with hatchling and uploads with twine.

It does **not** touch `CHANGELOG.md`, `uv.lock`, `docs/`, or the skill submodule. Those
are steps 3–5 and they are entirely manual.

**Requirements.** The pipeline shells out to `python -m build` and `python -m twine`, so
it needs the `dev` extras installed and that interpreter on `PATH`. A PyPI token must be
configured the way twine expects (`~/.pypirc` or `TWINE_*` environment variables).

**If the version was already bumped by hand** during implementation (steps 2–3),
`inv release` would bump it a second time. Pass the intended version explicitly
(`inv release --new-version x.y.z`), or run the build, upload, and tag steps separately.

**Clean `dist/` before building.** The upload step publishes everything in `dist/`, so
stale artifacts from a previous release would be re-uploaded and rejected. `inv build`
cleans first; a manual build may not.

## Do not reintroduce hardcoded versions

`krules_core.__version__` is derived from the installed package metadata, making
`pyproject.toml` the single source of truth. A hardcoded copy previously drifted to
`2.0.0` and stayed there across five releases without anyone noticing.

For the same reason, avoid restating the current version in prose (`README.md`,
`CLAUDE.md`, documentation headers). Reference the concept, not the number.

## Why the manual steps matter

Two releases show what slips when they are skipped:

- **3.2.1** was published with no `CHANGELOG.md` entry and left `uv.lock` pinned to
  `3.2.0`. Both were reconstructed in 3.2.2.
- **3.2.0** introduced `origin_id` while the skill kept declaring 3.0 for three weeks —
  the episode that led to mounting the skill as a submodule.
