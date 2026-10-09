# ADR-0005: Local worker pairing & authorization

- **Status:** Accepted
- **Date:** 2026-10 (baseline decision)
- **Owner:** Core backend (auth, policies), Execution layer (local worker)

## Context

The spec requires: "Local computer control must use an explicitly paired and
authorized local worker. A remote server must not gain unrestricted access to a
user's computer."

This is the security boundary between the **platform** (possibly remote, in
deployment modes B and C) and the **user's machine**. It must hold even when the
backend itself runs on a server the user does not control.

## Decision

### Pairing (explicit, user-visible, revocable)

The local worker on the user's machine enters a **pairing flow** before it will
accept any command:

1. The user initiates pairing from the client ("Pair this computer").
2. The worker and the backend/another client exchange a device-code/QR challenge
   (OIDC device flow; backend-mode C) **or** a local-only secret (modes A/B).
3. The worker stores the peer's public key; the peer stores the worker's.
   Both ends persist the pairing record (worker ID, fingerprint, created time).
4. Pairing is **revocable**: either side can revoke, immediately invalidating
   commands. Revocation is logged to the audit log.

### Authorization model (defense in depth)

Every computer operation is gated by three independent checks, in order:

1. **Pairing** — the requesting peer must be the paired identity (or a chain of
   trust to it). An unpaired/untrusted server gets `Failure(auth)` and no
   operation executes.
2. **Policy engine** (per-capability allowlists) — e.g. `shell.commands`,
   `fs.paths`, `apps.launch`. An operation outside the allowlist is rejected
   before any process is spawned. Policies live in core backend (C5) and are
   synced to the worker.
3. **Interactive approval** (for high-risk ops) — the client shows the user a
   prompt ("JARVIS wants to run `rm -rf ...`") and waits for explicit consent
   before the worker executes. Consent is one-shot, per command, and audited.

No operation is ever "best-effort approved"; an approval applies to exactly one
command invocation.

### Remote server cannot gain unrestricted access

- The worker refuses commands from any peer not in its pairing store.
- The worker's default posture is **deny**: capabilities are granted by explicit
  policy, never by default.
- The backend (even in mode C) does not hold the worker's credentials; it can
  only *request* an operation through the same policy+approval path as any other
  peer.
- Screenshot/input capabilities (matrix B7/B8, P2) additionally require the OS
  permission (TCC / consent / portal) at the worker — the worker cannot be
  coerced into bypassing the OS gate.

### Audit

Every accepted *and* every rejected operation writes an audit record: timestamp,
peer identity, capability, command/target, policy decision, approval actor
(user/human) if applicable, outcome. Audit records are append-only (matrix C5).

## Consequences / mitigations

- **Usability cost:** pairing + approval add friction. Mitigated by: remember-
  per-capability allowlists with user-set defaults, and fast local-mode pairing
  (no server round-trip in mode A).
- **Key management:** worker identity keys stored via OS keychain (D2), rotated
  on re-pair.
- **Testing:** property/unit tests for the three-gate order; integration test
  that an unpaired server is refused end-to-end (matrix C1/C5).

## Links

- Portability matrix C1 (auth/pairing), C5 (policies & audit)
- ADR-0004 (deployment modes; mode C requires pairing)
- Repository layout `backend/app/core/auth`, `backend/app/core/policies`,
  `backend/app/execution/workers`