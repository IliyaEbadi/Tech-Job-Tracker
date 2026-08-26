# Test fixtures

These JSON files are **hand-written samples** that copy the *shape* of the real
Greenhouse, Lever and Ashby responses. The companies, job ids and descriptions
are invented.

They exist so the test suite can run offline and stay deterministic: no test in
this project calls a live job board. Fixture data never reaches `data/jobs.json`
or the generated report.

| File | Mimics | Covers |
|---|---|---|
| `greenhouse_board.json` | `boards-api.greenhouse.io/v1/boards/<token>/jobs` | escaped HTML descriptions, multi-city locations, senior and non-tech titles that must be filtered out |
| `lever_postings.json` | `api.lever.co/v0/postings/<company>` | millisecond timestamps, empty `location` with an `allLocations` list, empty plain-text descriptions |
| `ashby_board.json` | `api.ashbyhq.com/posting-api/job-board/<org>` | `isListed: false` drafts, remote-in-Canada vs. other-province locations |
