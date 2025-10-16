# AI Performance Web

Lightweight Flask web application providing assisted performance engineering utilities around JMeter, Postman collections, HAR recordings and APM (Kibana) resources, enhanced by OpenAI and Anthropic models.

## DualMind AI Assistant (Business + Technical)
DualMind provides two coordinated AI personas over the same performance data to serve distinct stakeholder needs.

### Personas
- Business AI Assistant: Generates executive summary, pass/fail against standards, business risk level (Low/Moderate/High), release readiness recommendation, high-level capacity and stability narrative, highlights of Chaos Experiments outcomes.
- Technical AI Assistant: Produces deep diagnostics (slow endpoints, error patterns, correlation candidates), root-cause hypotheses, remediation actions (code, infra, cache, DB), environment tuning (threads, ramp, thresholds), resource utilization interpretation (CPU/Memory from Kibana), and prioritised technical backlog items.

### Output Structure (recommended)
1. EXECUTIVE SUMMARY (Business)
2. RELEASE READINESS & RISK (Business)
3. PERFORMANCE BOTTLENECKS (Technical)
4. ERRORS & STABILITY (Technical)
5. RESOURCE UTILIZATION (Technical)
6. CHAOS EXPERIMENTS OUTCOME (Business + Technical blend)
7. ACTIONABLE RECOMMENDATIONS (Merged, ordered by impact vs effort)

### Workflow
1. Data ingestion: JMeter statistics.json + dashboard.js extracts + optional Kibana metrics + chaos form fields.
2. Pre-processing: Numeric normalization, column reduction, error JSON extraction, CPU/Memory time-range derivation.
3. Dual persona prompting: Same sanitized dataset passed to two prompt templates (one business, one technical). Currently helper functions (`ask_gpt*`, `ask_claude*`) can be split into `ask_business_ai` and `ask_technical_ai` variants.
4. Aggregation: Merge sections; ensure consistent heading casing; strip unsupported markup.
5. Injection: HTML sections appended near end of report before Thank You image.

### Invocation Pattern
- UI checkboxes: `use_gpt` (stats/errors) and future `use_dualmind_business`, `use_dualmind_technical` can toggle each persona independently.
- Fallback: If one provider fails (timeout/API error) auto-fallback to the other for that persona.
- Determinism: Temperature kept low for Technical Assistant for repeatability; Business Assistant may allow slightly higher temperature for narrative richness.

### Extensibility
- Add additional personas (e.g., Security Performance Assistant) by cloning prompt scaffold.
- Centralize persona prompt templates in a registry dict to allow dynamic enable/disable.
- Implement latency/token logging per persona for cost/performance monitoring.
- Provide JSON mode output (keys: summary, bottlenecks, recommendations) to enable downstream automation.

### Implementation Hints
- Abstract current single-role prompts into two clearly named functions.
- Normalize headings via a small mapping before HTML insertion.
- Guard against oversized responses (truncate or summarize if > N chars).
- Sanitize any unexpected HTML tags returned by models.

## Key Features

1. JMeter Report Generator
   - Upload a JMeter HTML (or zip) report and enrich it.
   - Rewrites dashboard (branding, custom metadata, findings section with basic markup parsing).
   - Removes / reshapes APDEX & statistics columns (median, 95th, 99th pct, fail removed) and adds color coding for 90th percentile & error rate vs thresholds.
   - Optional AI statistics analysis (OpenAI) and error pattern investigation.
   - Optional Kibana APM CPU / Memory utilization extraction for a selected service and AI summarization.
   - Optional Chaos Experiments section (dynamic count, per experiment status, description, badge coloring).

2. Correlations Toolkit
   - Upload a JMeter XML test plan; extract potential correlation candidates (dynamic values).
   - AI assisted generation of an updated JMX with correlation logic (Claude or OpenAI).

3. Postman Collection Utilities
   - Structural analysis (methods, hosts, endpoints) of a Postman collection.
   - Conversion to a basic JMeter Test Plan (.jmx) without AI.
   - AI assisted conversion (Claude or OpenAI) with correlation hints.

4. HAR Conversion
   - Upload a HAR recording and selectively include base URLs, HTTP methods, path extensions.
   - Generate a JMeter recording-style XML or a runnable Test Plan JMX.
   - Optional grouping of requests into Transaction Controllers.

5. Usage Statistics
   - Simple JSON-based counters for feature usage displayed on the home page.

6. Branding & Report Enhancements
   - Custom cover, thank you page, logos.
   - Structured test scope, findings formatting (bold, bullets, numbered lists, indentation preservation).

## Technology Stack
- Python / Flask
- OpenAI Python SDK
- Anthropic Python SDK
- BeautifulSoup (HTML parsing)
- Requests (Kibana APM calls)

## Security & Configuration
Do NOT commit real API keys. The sample `config.py` contains hard coded keys for local testing only; replace with environment variables.

### Required Environment Variables
- `OPENAI_API_KEY` – OpenAI access key.
- `ANTHROPIC_API_KEY` – Anthropic access key.
- `SECRET_KEY` – Flask session secret.

Optional tunables can be placed in `.env` (loaded via `python-dotenv`). Remove hard coded keys from `config.py` before production use.

## Installation
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py  # starts server on http://0.0.0.0:5001
```

## Basic Workflow Examples
1. Generate Enriched Report: Navigate to /report-generator, upload JMeter zip, fill metadata, enable AI options as needed, download enriched zip.
2. Correlate JMeter: Go to /correlations, upload XML, view extracted tokens, optionally generate AI-enhanced JMX.
3. Postman to JMX: /postman-tools, upload collection, analyze or convert (with/without AI).
4. HAR to JMeter: /har-to-jmeter, upload HAR, select filters, export recording XML or test plan JMX.

## Kibana APM Integration
Provide service name and enable resource analysis. Application logs diagnostic decisions and inserts AI summarized CPU / Memory utilization block if data is retrieved.

## Chaos Experiments Section
Specify count and per-experiment title / status / description fields to embed structured experiment results in the final report.

## Extensibility Notes
- Add new AI providers by abstracting current `ask_*` helper functions.
- Enhance correlation rules by expanding parsing logic in `correlation_utils.py`.
- Replace direct Kibana login flow with OAuth / API token for production.

## Limitations
- Basic HTML string replacements (fragile against major JMeter template changes).
- Hard-coded model names; externalize if frequent model rotation is needed.
- Kibana integration depends on internal structure and may break with version changes.

## Recommended Next Steps
- Remove hard coded secrets.
- Add automated tests.
- Containerize with proper multi-stage build and secret injection.
- Add role-based access if exposed beyond internal network.

## License
Internal / proprietary usage. Add a license file if distribution scope changes.
