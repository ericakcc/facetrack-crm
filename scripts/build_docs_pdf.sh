#!/usr/bin/env bash
# Render docs/PRD.md and docs/TDD.md to PDF for AI Fund panel review.
# Uses pandoc -> standalone HTML (with CJK-aware CSS) -> Chrome headless -> PDF.
# Requires: pandoc, Google Chrome.
#
# Two CSS profiles:
#   - print-comfortable.css: PRD (lower density, easier on the eye, fills ~2 pages)
#   - print-tight.css:       TDD (higher density to fit the panel's 1-2 page rule)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS_DIR="${REPO_ROOT}/docs"
BUILD_DIR="${REPO_ROOT}/.docs-pdf-build"
mkdir -p "${BUILD_DIR}"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

shared_css_head() {
cat <<'CSS_EOF'
html {
  font-family: -apple-system, "Helvetica Neue", "PingFang TC", "Noto Sans CJK TC", "Microsoft JhengHei", sans-serif;
  color: #1a1a1a;
}
body { margin: 0; }
p { text-align: justify; }
li { text-align: justify; }
code { font-family: "JetBrains Mono", "SF Mono", Menlo, monospace; background: #f3f3f3; padding: 0 3px; border-radius: 3px; }
pre { background: #f6f6f6; border: 1px solid #e0e0e0; border-radius: 3px; page-break-inside: avoid; overflow-x: auto; }
pre code { background: transparent; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; page-break-inside: avoid; }
th, td { border: 1px solid #c5c5c5; vertical-align: top; }
th { background: #efefef; text-align: left; }
blockquote { border-left: 3px solid #cdcdcd; color: #555; }
img { max-width: 100%; }
hr { display: none; }
a { color: #0b5fbf; text-decoration: none; }
header.title-block-header, h1.title { display: none; }
CSS_EOF
}

# ----- Comfortable layout (PRD) -----
comfortable_css="${BUILD_DIR}/print-comfortable.css"
{
  shared_css_head
  cat <<'CSS_EOF'
@page { size: A4; margin: 16mm 16mm 16mm 16mm; }
html { font-size: 10.2pt; line-height: 1.5; }
h1 { font-size: 16pt; border-bottom: 1.5px solid #333; padding-bottom: 3px; margin: 0 0 0.5em; }
h2 { font-size: 12pt; margin: 1.05em 0 0.35em; border-bottom: 1px solid #aaa; padding-bottom: 1.5px; }
h3 { font-size: 10.6pt; margin: 0.75em 0 0.25em; font-weight: 700; }
h4 { font-size: 10.2pt; margin: 0.55em 0 0.18em; font-weight: 700; }
p  { margin: 0.4em 0 0.65em; }
li { margin: 0.12em 0; }
code { font-size: 9pt; }
pre { padding: 8px 10px; font-size: 8.6pt; line-height: 1.3; margin: 0.5em 0; }
table { margin: 0.5em 0 0.85em; font-size: 9.4pt; }
th, td { padding: 4px 7px; }
blockquote { margin: 0.55em 0; padding: 0.18em 0.85em; }
ul, ol { padding-left: 1.25em; margin: 0.4em 0 0.7em; }
CSS_EOF
} > "${comfortable_css}"

# ----- Tight layout (TDD) -----
tight_css="${BUILD_DIR}/print-tight.css"
{
  shared_css_head
  cat <<'CSS_EOF'
@page { size: A4; margin: 9.5mm 11mm 9.5mm 11mm; }
html { font-size: 8.3pt; line-height: 1.25; }
img { max-width: 100%; max-height: 175px; width: auto; display: block; margin: 0.25em auto; }
h1 { font-size: 12pt; border-bottom: 1.1px solid #333; padding-bottom: 1.5px; margin: 0 0 0.3em; }
h2 { font-size: 9.6pt; margin: 0.7em 0 0.15em; border-bottom: 1px solid #aaa; padding-bottom: 0.5px; }
h3 { font-size: 8.7pt; margin: 0.5em 0 0.12em; font-weight: 700; }
h4 { font-size: 8.3pt; margin: 0.35em 0 0.08em; font-weight: 700; }
p  { margin: 0.18em 0 0.3em; }
li { margin: 0.03em 0; }
code { font-size: 7.4pt; padding: 0 2px; }
pre { padding: 3.5px 5.5px; font-size: 6.9pt; line-height: 1.18; margin: 0.25em 0; }
table { margin: 0.25em 0 0.4em; font-size: 7.6pt; }
th, td { padding: 1.8px 4px; }
blockquote { margin: 0.3em 0; padding: 0.06em 0.55em; }
ul, ol { padding-left: 1em; margin: 0.18em 0 0.35em; }
CSS_EOF
} > "${tight_css}"

render() {
  local md_path="$1"
  local title="$2"
  local css_path="$3"
  local out_pdf="$4"
  local html_path="${BUILD_DIR}/$(basename "${md_path%.md}").html"

  pandoc "${md_path}" \
    --from=gfm \
    --to=html5 \
    --standalone \
    --embed-resources \
    --resource-path="$(dirname "${md_path}")" \
    --metadata "title=${title}" \
    --css="${css_path}" \
    -o "${html_path}"

  "${CHROME}" \
    --headless=new \
    --disable-gpu \
    --no-pdf-header-footer \
    --print-to-pdf="${out_pdf}" \
    --no-margins \
    "file://${html_path}" \
    >/dev/null 2>&1

  echo "Wrote ${out_pdf}"
}

render "${DOCS_DIR}/PRD.md" "FaceTrack CRM — PRD" "${comfortable_css}" "${DOCS_DIR}/PRD.pdf"
render "${DOCS_DIR}/TDD.md" "FaceTrack CRM — TDD" "${tight_css}"       "${DOCS_DIR}/TDD.pdf"
