---
name: initialize-ok-script-app
description: Initialize a repository created from the ok-script-app template for a Windows, Android-emulator, or browser game. Use when Codex needs to collect project requirements and configure app identity, runtime targets, icons, update repositories, the first automation task, MkDocs documentation, MirrorChyan integration, and GitHub tag-based packaging.
---

# Initialize an ok-script App

Configure the cloned template only after collecting the user's project details.

## Gather requirements first

Before editing files, ask the user for the following information in one concise questionnaire:

1. Game name and desired application name/title.
2. Runtime target(s): native Windows game, Android emulator/device, browser, or any combination. Require at least one.
3. For Windows: executable filename(s) and window class, if known.
4. For Android: package name(s) and emulator type, if known.
5. For browser: initial URL, display name, and browser resolution.
6. Source repository URL and update strategy: a dedicated update repository or the source repository during early testing.
7. Replacement `icon.png` and `icon.ico` files, or whether to keep the placeholders temporarily.
8. First task: class name, user-visible name, one-time or background trigger, and a short description of its behavior.
9. Whether to integrate MirrorChyan and, if so, its resource ID and upload-token secret name.
10. Supported aspect ratio/minimum resolution and any project/community links, if known.

Allow unknown optional values. Offer to retain safe template defaults or inspect runtime information later. Do not invent executable names, package names, repository URLs, or icons.

## Inspect before editing

- Read `README.md`, `src/config.py`, `pyappify.yml`, `mkdocs.yml`, `.github/workflows`, relevant files under `src/tasks`, and the relevant Chinese and English pages under `docs`.
- Check `git status` and preserve unrelated user changes.
- Search for remaining `ok-script-app`, `ok-oldking`, template repository URLs, and template-only release integrations.
- Use the repository-local `.venv` for Python commands when it exists.

## Apply the initialization

1. Update `src/config.py`:
   - Set `gui_title` and relevant `links`.
   - Configure `windows.exe` and `windows.hwnd_class` only from supplied values.
   - Configure `adb.packages` only from supplied values.
   - Configure `browser.url`, `browser.nick`, and `browser.resolution` only from supplied values.
   - Require at least one of `windows`, `adb`, or `browser`; retain every target type the user wants to support.
   - Adjust `supported_resolution` when specified.
   - Keep compatible capture and interaction defaults unless the user requests or the target requires a change.
2. Replace `icons/icon.png` and `icons/icon.ico` from user-provided assets. Keep their filenames unless there is a reason to rename them, and synchronize all references if renamed.
3. Update `pyappify.yml`:
   - Set the application and profile names.
   - Point each `git_url` to the chosen source or dedicated update repository.
   - Preserve Python 3.12 unless the project has a verified reason to change it.
4. Review `.github/workflows/build.yml`:
   - Replace project-specific repository URLs, artifact names, release links, and Git identity.
   - For a dedicated update repository, configure the sync target around the user's chosen secret names and clearly report which repository secrets must be created.
   - For source-repository testing, remove or disable update-repository sync steps that require unavailable template secrets.
   - If using MirrorChyan, update `mirrorchyan_uploading.yml` and `mirrorchyan_release_note.yml` with the user's owner, repository, resource ID, installer filename, and secret name; retain the dispatch steps in `build.yml`.
   - If not using MirrorChyan, delete both MirrorChyan workflow files and remove their dispatch step from `build.yml`.
   - Remove CNB integration when the user does not use it.
5. Create the first task under `src/tasks` and register its module/class pair in `onetime_tasks` or `trigger_tasks` in `src/config.py`.
   - Follow the repository's `$ok-script-tasks` skill for task structure.
   - Use `$ok-script-codegen` when implementing automation actions from a behavior description or screenshots.
   - Keep user-facing task strings translatable and use `$ok-script-i18n` when translations are requested.
6. Update the documentation site:
   - Set `site_name`, `site_description`, `repo_name`, `repo_url`, and `edit_uri` in `mkdocs.yml` from the initialized project.
   - Update template identity, repositories, installer names, targets, links, and setup details in both the Chinese pages under `docs/` and the English pages under `docs/en/`.
   - Keep the two languages structurally aligned and update `mkdocs.yml` navigation when pages are added, moved, or removed.
   - Retain `.github/workflows/docs.yml` when the user wants GitHub Pages; otherwise explain that it may be removed.
7. Keep `README.md` and `README_en.md` as concise repository landing pages that link to the canonical MkDocs documentation.

## Verify

- Parse modified Python files with `python -m compileall` or run the relevant tests using the local `.venv`.
- Validate YAML syntax when a YAML parser is available.
- Install `requirements-docs.txt` in the local `.venv` and run `python -m mkdocs build --strict` after documentation changes.
- Run `python main_debug.py` only when launching the GUI is appropriate for the environment.
- Search again for stale template names and URLs; distinguish intentional upstream documentation/action references from project-specific leftovers.
- Show the resulting diff and summarize any values still awaiting user input.

Do not create or push a tag unless the user explicitly asks to release. When requested, use a semantic tag such as `v0.1.0`; `.github/workflows/build.yml` triggers on `v*`.
