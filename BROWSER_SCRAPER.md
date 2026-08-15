# Browser-Based Instagram Scraper

This project now includes two scraping methods:

## 1. Browser-Based Scraper (Playwright)

**File**: `src/cookbook/browser_scraper.py`

### Features

- Uses Playwright to load the Instagram profile page with a real browser
- Automatically logs in using credentials from `.env` or config
- Extracts post data from the rendered page without using Instagram's API
- Bypasses Instagram's API rate limiting
- More resilient to Instagram's anti-scraping measures

### Configuration

Set `use_browser = true` in `cookbook.toml`:

```toml
username = "lizapanelim"
use_browser = true
```

### Requirements

- Playwright (installed via `uv sync`)
- Chromium browser (installed via `uv run playwright install chromium`)
- Valid Instagram credentials in `.env` (recommended but not strictly required for public profiles)

### How It Works

1. Launches a headless Chromium browser
2. Attempts to login using credentials from `INSTAGRAM_USERNAME` and `INSTAGRAM_PASSWORD`
3. Navigates to the target profile
4. Scrolls down to trigger post loading
5. Extracts post shortcuts from page HTML
6. Visits each post individually to extract engagement metrics and timestamps
7. Returns the collected posts

### Advantages

- Avoids Instagram API rate limiting completely
- Works with heavily automated detection protection
- Can scrape public profiles without authentication

### Browser Limitations

- Slower than API-based approach (requires full page loads)
- Instagram's login detection may block automation attempts
- Requires browser resources
- May require periodic updates to handle Instagram page structure changes

### Troubleshooting

#### No Posts Found on Profile

- The profile might be private or posts disabled
- Instagram might be blocking the automated browser
- Try clearing the browser cache: `rm -rf ~/.ms-playwright`

#### Login Fails

- Instagram's login page structure changes frequently
- The account might have 2FA enabled
- Try disabling 2FA on the test account

## 2. API-Based Scraper (Instaloader)

**File**: `src/cookbook/main.py` (when `use_browser = false`)

### API Configuration

Set `use_browser = false` in `cookbook.toml`:

```toml
username = "lizapanelim"
use_browser = false
```

### API Features

- Uses the `instaloader` library
- Interacts with Instagram's official endpoints
- Supports session management to reduce login frequency
- Built-in retry logic with exponential backoff

### API Limitations

- Subject to Instagram's aggressive rate limiting
- Requires valid authentication
- May be blocked after a few requests

## Switching Between Methods

### Use the Browser Scraper

```toml
use_browser = true
```

### Use the API Scraper

```toml
use_browser = false
```

## Performance Comparison

| Method | Speed | Rate Limit | Reliability | Resources |
| --- | --- | --- | --- | --- |
| Browser | Slow (5-30s per post) | No | Medium | High (browser process) |
| API | Fast (1-2s per post) | Yes | High* | Low |

*Reliability depends on rate limiting status

## Future Improvements

- [ ] Implement cookie-based login persistence for browser scraper
- [ ] Add proxy support for distributed scraping
- [ ] Implement cache for extracted posts
- [ ] Add selective field extraction to speed up browser scraper
- [ ] Implement retry logic for browser scraper
- [ ] Add support for Stories and Reels
