# GaleFling — Task Completion Checklist

After every code or docs change (unless user explicitly says to skip):

1. **Lint:** `.venv/Scripts/python.exe -m ruff check src tests` — must pass clean
2. **Tests:** `.venv/Scripts/python.exe -m pytest tests/ --cov=src` — must pass
3. **Fix any failures** before concluding

For a **release** (when bumping version):
1. Bump version in all 5 files: constants.py, default_config.json, installer.nsi, version_info.txt, README.md
2. Add CHANGELOG entry at top
3. Update README Release Build badge tag to `branch=vX.Y.Z`
4. Commit: `Release vX.Y.Z`
5. Tag: `vX.Y.Z`
6. Push master + tags
7. Build exe: `.venv/Scripts/python.exe -m PyInstaller build/build.spec --noconfirm`
8. Build installer: `"C:/Program Files (x86)/NSIS/makensis.exe" build/installer.nsi`

**Note:** User (Jas) sometimes says "no commits" — in that case skip steps 4-6 but still build.
