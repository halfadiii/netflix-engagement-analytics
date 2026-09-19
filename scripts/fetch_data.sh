#!/usr/bin/env bash
# Downloads the raw public source files this project is built on.
# Netflix's CDN blocks requests without a real browser User-Agent, so all
# three curl calls send one.
set -euo pipefail

RAW_DIR="$(dirname "$0")/../data/raw"
mkdir -p "$RAW_DIR"
cd "$RAW_DIR"

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
HDRS=(-H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      -H "Accept-Language: en-US,en;q=0.9"
      -H "sec-fetch-dest: document" -H "sec-fetch-mode: navigate" -H "sec-fetch-site: none")

echo "Fetching Netflix Top 10 (global, weekly, all history)..."
curl -sL -A "$UA" "${HDRS[@]}" -o all-weeks-global.tsv \
  "https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv"

echo "Fetching Netflix Top 10 (by country, weekly, all history - ~30MB)..."
curl -sL -A "$UA" "${HDRS[@]}" -o all-weeks-countries.tsv \
  "https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv"

echo "Fetching 'What We Watched' engagement reports (last 3 half-years)..."
curl -sL -A "$UA" -o "Netflix-What-We-Watched-2025Jan-Jun.xlsx" \
  "https://assets.ctfassets.net/4cd45et68cgf/mplcXj5ulHDfbCPCr0f0I/5dbb6ec09f03df89706476e380e9b8bd/What_We_Watched_A_Netflix_Engagement_Report_2025Jan-Jun.xlsx"
curl -sL -A "$UA" -o "Netflix-What-We-Watched-2025Jul-Dec.xlsx" \
  "https://assets.ctfassets.net/4cd45et68cgf/2vdDPGLKA0XX2cjF2APJFn/7f1c367b39ed73a6a588751d3c5d0252/What_We_Watched_A_Netflix_Engagement_Report_2025Jul-Dec__6_.xlsx"
curl -sL -A "$UA" -o "Netflix-What-We-Watched-2026Jan-Jun.xlsx" \
  "https://assets.ctfassets.net/4cd45et68cgf/40WGcHJa9vRua31kU6Gbz5/43b15c7fbd6924392fc80e885839e39f/Netflix-s_What_We_Watched_Report_2026Jan-Jun__1_.xlsx"

echo "Done. Files in $RAW_DIR:"
ls -la
echo ""
echo "Note: Netflix's download links for the engagement report change with each"
echo "new half-year release. If a .xlsx URL above 404s, get the current link from"
echo "https://about.netflix.com/en/news/what-we-watched-a-netflix-engagement-report"
echo "and update it here."
