# App and Runtime Target Configuration

## App Settings

Review at least these settings in `src/config.py`:

- `gui_title`: application window title.
- `gui_icon`: GUI icon path.
- `supported_resolution`: supported aspect ratio and minimum resolution.
- `links`: project, support, and community links.
- `onetime_tasks`, `trigger_tasks`: task registration lists.

## Runtime Targets

Configure at least one of `windows`, `adb`, or `browser`. A project may support multiple target types.

### Native Windows Game

Configure these `windows` values:

- `exe`: game executable filenames.
- `hwnd_class`: optional window class for more accurate matching.
- `interaction`: allowed input methods in priority order.
- `capture_method`: allowed capture methods in priority order.
- HDR and background-capture options.

### Android Emulator or Device

Add package names to `adb.packages`. MuMu can use native capture and input; other emulators and devices generally use ADB.

### Browser Game

Uncomment the `browser` example and set:

```python
'browser': {
    'url': 'https://example.com/game',
    'nick': 'Browser',
    'resolution': (1280, 720),
},
```

Browser targets also require `playwright`. Add it to each applicable profile in
`pyproject.toml`, then recompile the corresponding `requirements.txt` or
`requirements-web.txt` so local and GitHub build environments install it.

## Replace Icons

Replace `icons/icon.png` and `icons/icon.ico`. Keeping the filenames avoids extra configuration. If they change, update their paths in `src/config.py` and `pyappify.yml`.

## Update Repositories

Edit the app name, profile names, and `git_url` values in `pyappify.yml`:

- Use a separate lightweight update repository for production.
- The source repository can be used during early testing.
- With a separate update repository, update the sync targets and secrets in `.github/workflows/build.yml`.

After initialization, search for stale `ok-script-app`, `ok-oldking`, repository URLs, installer names, and community links inherited from the template.
