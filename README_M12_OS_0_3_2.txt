M12 OS 0.3.2

Updater is now workable:
1. Check GitHub update.json
2. Download ZIP
3. Create backup in backups/
4. Install files from downloaded ZIP
5. Preserve data/, logs/, updates/, backups/, .venv/, .git/, and config/settings.json
6. Restart M12 OS

For GitHub release testing, update your GitHub update.json with a higher version and a zip_url.
Example:
{
  "version": "0.3.3",
  "notes": "Test update",
  "zip_url": "https://github.com/aryaboy7/M12_05/archive/refs/heads/main.zip"
}
