# Test Results

## Latest Verified Checkpoints

- **Alembic head:** `0011_remove_retired_features` applied successfully.
- **Backend regression suite:** `57 passed` when excluding only the two integration tests that require unreachable NVIDIA embedding service access in this environment.
- **Frontend TypeScript:** `PASSED` with `--noUnusedLocals --noUnusedParameters`.
- **Frontend production build:** `PASSED` with 11 routes; the retired `/reliability` route is absent.
- **Retired-feature source scan:** no matches remain in application, test, or frontend source; migration cleanup retains only the historical identifiers needed to remove old database objects.
