# Monster Energy Deal Tracker 🔋⚡

Automated price tracking system for Monster Energy drinks across major online retailers.

## Features

- 🔍 Automatically checks Amazon (and Walmart with setup) for Monster Energy deals
- 📊 Tracks price history over time
- 🚨 Creates GitHub Issues when prices drop below $0.12/fl oz
- ⏰ Runs automatically twice daily via GitHub Actions
- 📈 Maintains price history in JSON format
- 🆓 Completely free to run

## Setup

### 1. Clone and Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/monster-deal-tracker.git
git push -u origin main
```

### 2. File Structure

```
monster-deal-tracker/
├── tracker.py              # Main scraping script
├── requirements.txt        # Python dependencies
├── price_history.json      # Price tracking database (auto-generated)
├── deal_report.md          # Latest report (auto-generated)
├── .github/
│   └── workflows/
│       └── tracker.yml     # GitHub Actions workflow
└── README.md
```

### 3. GitHub Actions Setup

The workflow is already configured! It will:
- Run automatically at 9 AM and 6 PM UTC daily
- Can be triggered manually from the "Actions" tab
- Commits price updates to the repo
- Creates Issues when deals are found

### 4. Enable GitHub Actions

1. Go to your repo → **Settings** → **Actions** → **General**
2. Under "Workflow permissions", select **Read and write permissions**
3. Click **Save**

## Configuration

Edit `tracker.py` to customize:

```python
self.price_threshold = 0.12  # Change alert threshold ($/fl oz)
```

Edit `.github/workflows/tracker.yml` to change schedule:

```yaml
schedule:
  - cron: '0 9,18 * * *'  # Modify timing here
```

## Manual Testing

Run locally:

```bash
pip install -r requirements.txt
python tracker.py
```

## Notifications

### GitHub Issues (Default)
- Automatic issue creation when deals found
- Subscribe to repo notifications

### Email Notifications
Add to your GitHub notification settings:
1. Watch the repository
2. Configure email notifications for Issues

### Alternative: Telegram/Discord
You can add webhook notifications by modifying the GitHub Actions workflow to send HTTP requests to Telegram/Discord webhooks.

## Limitations

- Amazon may occasionally block requests (rotating user agents helps)
- Walmart requires more advanced scraping (Selenium)
- Results depend on HTML structure (may need updates if sites change)

## Future Enhancements

- [ ] Add more retailers (Target, Costco)
- [ ] Implement Selenium for JavaScript-heavy sites
- [ ] Add Discord/Telegram bot notifications
- [ ] Create price trend visualizations
- [ ] Track specific Monster flavors
- [ ] Add unit tests

## Legal Note

This tool is for personal use only. Please respect retailers' Terms of Service and robots.txt. Consider rate limiting and don't hammer their servers.

## License

MIT License - Feel free to modify and use!