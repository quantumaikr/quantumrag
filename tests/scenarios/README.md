# QuantumRAG Scenario Test Versioning

## Folder Structure

```
tests/scenarios/
├── v1/                          # Baseline (107 cases, S1-S17)
│   └── test_cases.py            # Self-contained runner
├── v2/                          # Advanced (138 cases, S1-S25)
│   └── test_cases.py            # Self-contained runner
├── v3/                          # Future versions...
│   └── test_cases.py
└── README.md

docs/reports/
├── v1/
│   └── scenario-test-report.md  # v1 results
├── v2/
│   └── scenario-test-report.md  # v2 results
└── scenario-test-report.md      # Latest (symlink or copy)
```

## Versioning Strategy

- Each version is **self-contained** - no cross-imports between versions
- v1 cases (S1-S17) are preserved in every subsequent version for regression tracking
- New versions add scenarios, never remove baseline ones
- Reports include version comparison tables

## Running Tests

```bash
# Run latest (v1 baseline)
uv run python tests/run_scenario_tests.py

# Run specific version
uv run python tests/scenarios/v2/test_cases.py
```

## Version History

| Version | Scenarios | Cases | Key Changes |
|---------|-----------|-------|-------------|
| v1      | S1-S17    | 107   | Baseline with PDF/HWPX support |
| v2      | S1-S25    | 138   | +31 advanced cases (incomplete info, contradiction, mixed-lang, counterfactual, precision, complex conditional, abstract, reverse) |
