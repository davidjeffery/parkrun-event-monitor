# parkrun event monitor

Checks `https://images.parkrun.com/events.json` at 08:00 daily, and hourly Friday 18:00 through Saturday 08:00 **Europe/London** time. GitHub Actions triggers each UTC hour and Python gates execution in UK local time, including daylight-saving changes.

- First successful run establishes baseline without emailing historical events.
- Later successful runs email any newly appearing event IDs and their names, available area/country, coordinates and links.
- A failed fetch or email will not replace the last committed snapshot.
- Existing IDs are not alerted again after successful delivery.

## Install

Upload `monitor.py` to repository root, and `workflow.yml` to `.github/workflows/parkrun.yml`. GitHub's web editor can create new files with paths containing folders.

In repository **Settings → Secrets and variables → Actions → New repository secret**, set:

- `SMTP_USER`: Gmail account used to send (probably djeffery92@gmail.com)
- `SMTP_APP_PASSWORD`: 16-character **Gmail app password** (not your normal Gmail password). Google's two-step verification must be enabled, and app passwords must be available for the account.

The alert destination is `djeffery92@gmail.com` in the script. Do not enter secrets into ChatGPT or commit them to files.

Ensure repository **Settings → Actions → General → Workflow permissions** permits **Read and write permissions**. This is required so Actions can commit its last good snapshot back to the repository.

Go to **Actions → Check for new parkruns → Run workflow** once to establish your baseline. Later scheduled runs compare against `data/events_snapshot.json`, committed automatically.

Note: GitHub Actions cron executions can be delayed; GitHub may disable workflows in public repos after 60 days without repository activity. Snapshot commits from checks generally provide activity, but monitor the Actions tab periodically.
