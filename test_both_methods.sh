#!/bin/bash
# Test both scraping methods

set -e

echo "========================================"
echo "Instagram CLI - Dual Scraper Test"
echo "========================================"
echo

# Get the directory of this script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Test 1: API-based scraper
echo "Test 1: API-Based Scraper (Instaloader)"
echo "========================================"
echo "Updating config: use_browser = false"
sed -i.bak 's/use_browser = true/use_browser = false/' cookbook.toml
echo

echo "Running: uv run cookbook --config cookbook.toml"
echo
if uv run cookbook --config cookbook.toml; then
    echo
    echo "✓ API-based scraper succeeded!"
    echo
else
    echo
    echo "✗ API-based scraper failed (possibly rate-limited)"
    echo
fi

# Test 2: Browser-based scraper
echo
echo "Test 2: Browser-Based Scraper (Playwright)"
echo "========================================"
echo "Updating config: use_browser = true"
sed -i.bak 's/use_browser = false/use_browser = true/' cookbook.toml
echo

echo "Running: uv run cookbook --config cookbook.toml"
echo
if uv run cookbook --config cookbook.toml; then
    echo
    echo "✓ Browser-based scraper succeeded!"
    echo
else
    echo
    echo "✗ Browser-based scraper failed"
    echo
fi

# Restore original config
echo "Restoring original config..."
mv cookbook.toml.bak cookbook.toml

echo
echo "========================================"
echo "Test complete"
echo "========================================"
