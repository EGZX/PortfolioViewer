---
trigger: always_on
globs: "*test*,*_test.py,*.spec.*"
---

# Testing Standards

1.  **Test Behavior**: Test the behavior/interface, not the implementation details.
2.  **Independence**: Tests must be independent. No test should rely on the state left by another.
3.  **Mocking**: Mock external boundaries (APIs, complex DB interactions) to ensure tests are fast and deterministic.
4.  **Coverage**: Aim for high coverage on critical business logic/calculations.
5.  **Descriptive Names**: specific_behavior_when_condition_expected_result (e.g., `calculate_tax_returns_zero_when_income_below_threshold`).
