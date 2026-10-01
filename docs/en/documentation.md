# Build the Documentation Site

Documentation sources live in `docs/`; navigation and site settings live in `mkdocs.yml`. Generated HTML is written to the ignored `site/` directory.

## Local Preview

Install documentation dependencies in the project virtual environment:

```powershell
python -m pip install --index-url https://pypi.org/simple/ -r requirements-docs.txt
python -m mkdocs serve
```

Open `http://127.0.0.1:8000/`. The development server rebuilds pages when Markdown changes.

## Build Static HTML

```powershell
python -m mkdocs build --strict
```

`--strict` treats navigation and internal-link warnings as build failures. Publish the contents of `site/` on any static host.

## GitHub Pages

The repository includes `.github/workflows/docs.yml`:

1. Open **Settings → Pages** in the repository.
2. Set **Build and deployment → Source** to **GitHub Actions**.
3. Push to `master` or `main`, or run the `Docs` workflow manually.
4. Open the deployment URL from the workflow or Pages settings.

After creating a project from this template, update `site_name`, `site_description`, `repo_name`, `repo_url`, and `edit_uri` in `mkdocs.yml`.

## Layout

```text
mkdocs.yml                  MkDocs configuration and navigation
requirements-docs.txt      Documentation build dependencies
pyproject.toml             Source of truth for direct dependencies and profiles
docs/                       Chinese documentation
docs/en/                    English documentation
docs/images/                Shared images
.github/workflows/docs.yml  GitHub Pages build and deployment
site/                       Generated static HTML (ignored)
```

When adding a page, include it in `nav` in `mkdocs.yml` and run a strict build.
