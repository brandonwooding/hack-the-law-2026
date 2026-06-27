# Regulator PDF Ingestion

This pipeline imports regulator PDF pages into the existing legal graph without
creating `Regime` nodes. A regime remains an anchor `Act`/`Treaty` plus its graph
neighbourhood.

## Model

- Sector-facing guidance is stored as `(:Document:Guidance)`.
- Regulator policy/procedure material is stored as `(:Document:RegulatoryPolicy)`.
- Parsed PDF sections become `(:Provision)` nodes below the document via
  `CONTAINS`, so they participate in the existing provision full-text index.
- A regulator document enters a regime neighbourhood only when it has an explicit
  `ISSUED_UNDER` edge to an anchor Act/SI/provision.

The importer is conservative about those edges. It does not attach every Ofcom or
ICO corporate policy to a regime merely because the publisher is Ofcom or ICO.
The OCR text or title needs to identify a seeded Act.

## Source Pages

Only ingest regulator-facing legal/regulatory material. Do not use corporate
policy/procedure pages such as Ofcom internal policies or ICO staff policies;
those are not part of the regulated Online Safety Act neighbourhood.

When the source pages are known, configure them in `config/scope.yaml` under
`uk.regulator_documents` or add them to a purpose-built ingestion script.

Run only this adapter:

```bash
uv run legalgraph fetch --sources uk-regulator-documents
```

Then run the normal graph passes:

```bash
uv run legalgraph load
uv run legalgraph link
```

## OCR

By default `parse_with_nvidia` is `false`, so the adapter downloads PDFs and
emits metadata-only documents. This is useful for discovery and review.

To populate provision trees, either:

- place cached OCR JSON at `dataset/ocr/uk-regulator-documents/{doc_id}.json`, or
- set `parse_with_nvidia: true` on a page config and provide
  `NVIDIA_API_KEY` or `NGC_API_KEY`.

The CLI loads the project-root `.env`, so `NVIDIA_API_KEY` can live there;
it does not need to be exported in the shell.

NVIDIA Nemotron Parse is called through `model: "nvidia/nemotron-parse"`.
The documented request format is image-based, so the adapter renders PDF pages
to PNG with `pypdfium2`, sends each page to Nemotron Parse, then merges the page
outputs into the OCR JSON shape below. Use `parse_max_pages` during testing to
keep cost and latency bounded.

Expected OCR JSON shape:

```json
{
  "title": "Online Safety Act 2023 statutory guidance",
  "published_date": "2025-01-01",
  "updated_date": "2025-02-01",
  "version": "1.0",
  "text": "Full extracted text...",
  "sections": [
    {
      "number": "1",
      "heading": "Scope",
      "text": "Section text...",
      "page_start": 3,
      "page_end": 5,
      "children": []
    }
  ]
}
```

## Live Smoke Test

Using a temporary dataset on 2026-06-27:

- Ofcom: 22 PDFs discovered/downloaded, 2 stale PDF links skipped as 404.
- ICO: 30 PDFs discovered/downloaded.
- Output: 50 parsed document JSON files, 7 `Guidance`, 43 `RegulatoryPolicy`.
- With OCR disabled, all were metadata-only and unlinked to regimes.

## Online Safety Act Pack

`scripts/ingest_osa_regulator_docs.py` ingests the initial Online Safety Act
regulator pack:

Ofcom PDFs, parsed with NVIDIA Nemotron Parse and linked `ISSUED_UNDER` the
Online Safety Act 2023:

- Risk Assessment Guidance and Risk Profiles.
- Illegal content Codes of Practice for user-to-user services.
- Children's Risk Assessment Guidance and Children's Risk Profiles.
- Issued Protection of Children Code of Practice for user-to-user services.
- Online Safety Enforcement Guidance.

ICO HTML guidance, parsed directly and linked `ISSUED_UNDER` the Data Protection
Act 2018 while also tagged with the online-safety and data-protection concepts:

- Age appropriate design: a code of practice for online services.
- Children and the UK GDPR.

Run:

```bash
uv run python scripts/ingest_osa_regulator_docs.py
uv run legalgraph load
uv run legalgraph link
```

For a bounded test run:

```bash
OSA_REGDOC_MAX_PAGES=5 OSA_ICO_MAX_PAGES=5 uv run python scripts/ingest_osa_regulator_docs.py
```
