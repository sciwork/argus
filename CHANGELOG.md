## 1.0.0 (2026-10-11)

### BREAKING CHANGE

- replace DB_PATH with DATABASE_URL.

### Feat

- fold frontend dashboard into the monorepo (#18)
- add PostgreSQL database support (#12)
- replace raw SQL with SQLAlchemy ORM (#11)

### Perf

- remove SQLite CLI from container image (#13)

## 0.1.0 (2026-07-22)

### Feat

- redirect root URL to dashboard (#8)

### Fix

- exclude already-started events from registration report

## 0.0.1 (2026-05-16)

### Feat

- initial Argus webhook service with dashboard
