# Test Suite Summary

## Current seven-test comparison suite

| Test | One-sentence summary |
|---|---|
| **Finance** | Tests multi-step numerical analysis and report writing from stock CSV data, differentiating calculation accuracy from general summarization. |
| **Apache** | Tests operational log analysis, separating server configuration failures, client errors, security activity, and actionable recommendations. |
| **Access anomaly** | Tests deterministic rule application over event records, emphasizing exact threshold-based classification and JSON-only output. |
| **Compression** | Tests dense, faithful compression of a long research note while preserving uncertainty, sources, numbers, risks, and investment implications. |
| **Family note** | Tests natural, audience-appropriate explanation under word-count, phrase, forbidden-word, and sentence-count constraints. |
| **Checklist** | Tests structured instruction following across headings, bullet counts, word lengths, vocabulary limits, and exact document shape. |
| **Text lines** | Tests short-form formatting discipline across exact lines, sentence limits, bullet requirements, and required-word counts. |

## Auxiliary tests

- **Iris outliers:** Tests tabular anomaly detection, but it is not part of the current seven-test apples-to-apples chart.
- **Strict JSON / CSV / exact-line / constrained bullets:** Older IFEval diagnostics that isolate output-format obedience; useful for debugging instruction following, but too narrow to represent overall model quality.
