# 07 — Database Test Plan

Target: SQLAlchemy Models & Persistence Layer (`licensing_server/database.py`).

---

## 1. Schema & Model Test Targets
- **`UserDB`**: Unique email constraints, role defaults (`CUSTOMER`), `account_status` (`ACTIVE`/`BANNED`), session version increments.
- **`SubscriptionDB`**: Relationship to `UserDB`, plan tier enum enforcement, `device_limit` defaults.
- **`DeviceDB`**: Device fingerprint indexing, foreign key cascade rules on user deletion.
- **`CreditWalletDB`**: Integrity of credit balances (`subscription_credits`, `purchased_credits`, `credits_used`). Prevent negative balances.
- **`CreditTransactionDB`**: Append-only transaction ledger auditing credit spend and top-ups.
- **`LicenseEventDB`**: Event enum enforcement (`DEVICE_ACTIVATED`, `LOGIN`, `PAYMENT_VERIFIED`), timestamp ordering.

---

## 2. Integrity & Concurrency Verifications
- **Atomic Transactions:** Test rollback behavior on mid-operation exceptions (e.g., user created but subscription commit fails).
- **Concurrency Test:** Simulate simultaneous token deduction or device activation attempts against the same user record.
- **Slow Query Listener:** Verify that queries exceeding `SLOW_QUERY_THRESHOLD_MS` trigger warning events via SQLAlchemy event hooks.
