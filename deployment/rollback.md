# Rollback & Recovery Procedures

This document details the verified rollback mechanisms implemented in the CHARLIE codebase across server and client layers.

---

## 1. Rollback Architecture Overview

CHARLIE provides verified rollback capabilities at three tiers:

1. **Server Staged Release Rollback**: Immediate halting or revocation of distributed update packages.
2. **Client Automated Crash-Loop Rollback**: Automated restoration of prior binaries, local databases, and license tokens upon startup failure.
3. **Database Schema Rollback**: Backward-compatible non-destructive migrations.

---

## 2. Server-Side Release Rollback (Operational Runbook)

When an update deployed to the client fleet triggers elevated crash rates or regression issues, operations must follow the sequence in `UPDATE_EMERGENCY_ROLLBACK.md`:

### Step 1: Immediate Rollout Pause (< 2 Minutes)

Halts new client downloads without revoking the build:

```http
POST /updates/releases/{version}/pause
Host: licensing.charlie.ai
X-Admin-Key: <ADMIN_KEY>
```

**Effect**: Any client checking for updates receives a response indicating that the client is up to date. Download transfers are stopped immediately.

### Step 2: Release Revocation (< 5 Minutes)

Formally invalidates the release across the entire network:

```http
POST /updates/releases/{version}/revoke
Host: licensing.charlie.ai
X-Admin-Key: <ADMIN_KEY>
Content-Type: application/json

{
  "reason": "Critical startup exception in speech processing pipeline"
}
```

**Effect**: Any client that already downloaded the installer package will verify the status against the server prior to running `UpdateInstaller` and reject the upgrade with `RELEASE_REVOKED`.

---

## 3. Client-Side Automated Rollback (`update_rollback.py`)

The desktop client contains an embedded `RollbackManager` and `PreUpdateBackupManager`:

### Pre-Update Snapshot

Before any update binary is applied:

1. `PreUpdateBackupManager.create_snapshot(current_version)` executes.
2. Creates an archive in `{AppData}/CHARLIE/backups/`:
   - `pre_update_{current_version}_{timestamp}.zip`
3. Archives:
   - Configuration files (`config/*`)
   - Encrypted local license cache and checkpoints (`checkpoints/*`)
   - Snapshot metadata (`snapshot_meta.json`)
4. Stores rollback reference in `{AppData}/CHARLIE/updates/rollback_state.json`.

### Post-Update Health Check & Crash Loop Detection

1. On startup of the newly installed version, `PostUpdateHealthChecker.record_launch_attempt(version)` increments the launch attempt counter.
2. Core subsystems (GUI, audio, database, licensing) run verification checks.
3. If successful, `mark_health_validated(version)` flags the version as `LAST_KNOWN_GOOD`.
4. If startup crashes occur **3 consecutive times** (`max_attempts = 3`), `is_crash_loop()` evaluates to `True`.

### Automated Restoration

Upon crash loop detection:

1. `RollbackManager.execute_rollback()` triggers automatically.
2. Unpacks `pre_update_{current_version}_{timestamp}.zip`.
3. Restores configurations, data files, and license tokens to their exact previous state.
4. Restores previous executable binary.
5. Informs user:
   > *"The latest update could not start correctly. CHARLIE restored the previous working version."*

---

## 4. Database Migration & Rollback Considerations

### SQLite Schema Evolution

- Database schema changes in `licensing_server/database.py` (`init_db()`) are designed to be strictly **additive**:
  - `ALTER TABLE {table} ADD COLUMN {column}`
  - No column deletions or destructive renamings are performed.
- Previous server versions can safely run against a database upgraded by a newer version because all new columns are nullable or have defaults.

### What is NOT Implemented (Gaps & Limitations)

- **Alembic Down-Migrations**: The project does not currently use Alembic migration scripts (`alembic downgrade -1`). Rollback of server schema must be handled via full database backup restoration.
- **Automated Server Database Backup**: The server does not have an internal scheduled cron to dump `charlie_licensing.db`. Backups must be orchestrated at the OS/infrastructure level.
