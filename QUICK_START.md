#!/usr/bin/env bash
# Quick reference for Instagram scraper methods

cat << 'EOF'

╔════════════════════════════════════════════════════════════════════════════╗
║         Instagram Scraper - Quick Reference Guide                         ║
╚════════════════════════════════════════════════════════════════════════════╝

┌─ CURRENT STATUS ────────────────────────────────────────────────────────────┐
│                                                                              │
│  Active Configuration (cookbook.toml):  use_browser = false               │
│  Current Method:                        API-based (Instaloader)           │
│  Rate Limited:                          YES (401 "Please wait...")         │
│                                                                              │
│  Available Alternative:                 Browser-based (Playwright)         │
│  Status:                               Ready to use                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ METHOD 1: API-BASED SCRAPER (Instaloader) ─────────────────────────────────┐
│                                                                              │
│  USE WHEN:                                                                 │
│  • Instagram API is responding normally                                    │
│  • You want fast performance                                               │
│  • You have valid credentials                                              │
│                                                                              │
│  CONFIGURATION:                                                            │
│    cookbook.toml:                                                          │
│      use_browser = false                                                   │
│                                                                              │
│  COMMAND:                                                                  │
│    $ uv run cookbook --config cookbook.toml                                │
│                                                                              │
│  PROS:                                                                     │
│    ✓ Fast (1-2 seconds per post)                                           │
│    ✓ Efficient (low resource usage)                                        │
│    ✓ Session support (login once, reuse)                                   │
│    ✓ Retry/backoff built-in                                                │
│                                                                              │
│  CONS:                                                                     │
│    ✗ Subject to Instagram API rate limiting                                │
│    ✗ Currently rate-limited on this account                                │
│    ✗ Requires authentication                                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ METHOD 2: BROWSER-BASED SCRAPER (Playwright) ──────────────────────────────┐
│                                                                              │
│  USE WHEN:                                                                 │
│  • API is rate-limited (current situation!)                                │
│  • You need to bypass anti-scraping measures                               │
│  • Scraping public profiles                                                │
│                                                                              │
│  CONFIGURATION:                                                            │
│    cookbook.toml:                                                          │
│      use_browser = true                                                    │
│                                                                              │
│  SETUP (first time only):                                                  │
│    $ uv sync                              # Install playwright             │
│    $ uv run playwright install chromium   # Download browser               │
│                                                                              │
│  COMMAND:                                                                  │
│    $ uv run cookbook --config cookbook.toml                                │
│                                                                              │
│  PROS:                                                                     │
│    ✓ Bypasses API rate limiting completely                                 │
│    ✓ Works like a real user (harder to block)                              │
│    ✓ Can scrape public profiles without auth                               │
│    ✓ More resilient to Instagram changes                                   │
│                                                                              │
│  CONS:                                                                     │
│    ✗ Slower (5-30 seconds per post)                                        │
│    ✗ Higher resource usage (browser process)                               │
│    ✗ Login detection may fail (Instagram blocklists)                       │
│    ✗ Requires Playwright installation                                      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ SWITCHING BETWEEN METHODS ─────────────────────────────────────────────────┐
│                                                                              │
│  STEP 1: Edit cookbook.toml                                               │
│    $ nano cookbook.toml                                                    │
│                                                                              │
│  STEP 2: Change the use_browser line:                                     │
│                                                                              │
│    For API-based:      use_browser = false                                 │
│    For Browser-based:  use_browser = true                                  │
│                                                                              │
│  STEP 3: Save and run:                                                    │
│    $ uv run cookbook --config cookbook.toml                                │
│                                                                              │
│  TIP: Adjust other settings as needed:                                    │
│    • limit: Number of posts to fetch                                       │
│    • reverse: Sort chronologically (oldest first)                          │
│    • login_user: Username for authentication                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ RECOMMENDED WORKFLOW ──────────────────────────────────────────────────────┐
│                                                                              │
│  1. Try API-based first (fast, efficient):                                 │
│     Set use_browser = false                                                │
│                                                                              │
│  2. If you get rate-limited (401 error):                                   │
│     Switch to browser-based: use_browser = true                            │
│                                                                              │
│  3. If browser scraper has issues:                                         │
│     • Clear cache: rm -rf ~/.ms-playwright                                 │
│     • Check Instagram login selectors                                      │
│     • Try public profile without authentication                            │
│                                                                              │
│  4. Monitor rate limits:                                                   │
│     • API typically resets after 15-30 minutes                             │
│     • Browser has no limits (rate-limit-free!)                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ TROUBLESHOOTING ───────────────────────────────────────────────────────────┐
│                                                                              │
│  ERROR: "401 Unauthorized - Please wait..."                                │
│  → Instagram API rate limit. Switch to browser scraper (use_browser=true)  │
│                                                                              │
│  ERROR: "No posts found on profile"                                        │
│  → Profile is private or posts disabled                                    │
│  → Instagram detected automation, temporarily blocked                      │
│  → Try: rm -rf ~/.ms-playwright && uv run playwright install chromium     │
│                                                                              │
│  ERROR: "Could not find username field"                                    │
│  → Instagram login page changed                                            │
│  → Workaround: Scrape without authentication (public profiles only)        │
│                                                                              │
│  ERROR: Slow performance                                                   │
│  → Browser scraper is slower by design                                     │
│  → Reduce limit in config: limit = 1                                       │
│  → Or switch to API-based if rate limits allow                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ CONFIGURATION EXAMPLES ────────────────────────────────────────────────────┐
│                                                                              │
│  Fast API scraping (when not rate-limited):                                │
│  ┌─────────────────────────────────────────┐                               │
│  │ use_browser = false                     │                               │
│  │ limit = 10                              │                               │
│  │ request_delay_seconds = 1.5             │                               │
│  └─────────────────────────────────────────┘                               │
│                                                                              │
│  Slow but reliable browser scraping:                                       │
│  ┌─────────────────────────────────────────┐                               │
│  │ use_browser = true                      │                               │
│  │ limit = 5                               │                               │
│  │ login_user = ""  # optional             │                               │
│  └─────────────────────────────────────────┘                               │
│                                                                              │
│  Maximum wait for rate-limited API:                                        │
│  ┌─────────────────────────────────────────┐                               │
│  │ use_browser = false                     │                               │
│  │ max_fetch_attempts = 8                  │                               │
│  │ retry_wait_seconds = 600  # 10 minutes  │                               │
│  └─────────────────────────────────────────┘                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

EOF
EOF
