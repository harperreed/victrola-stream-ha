# victrola-stream-ha

## Names

The agent working this repo is **BIGFOOT BACKSPIN**. The human is **Doctor Biz**, a.k.a.
**Vinyl Diesel**.

## What this is

A Home Assistant custom integration (`victrola_stream`), installable via HACS, for the
Victrola Stream turntable. It talks to the device's NSDK HTTP API on port 80, tracks
platter and streaming state through a push-first coordinator, and offers the turntable's
live stream to Home Assistant media players.

## Commands

- `uv sync` — install the dev environment (Python >=3.14.2, Home Assistant 2026.9.x).
- `scripts/check` — the canonical check: ruff lint, ruff format check, pytest. Must pass
  before every commit.
- `scripts/e2e` — the live-device test suite. Talks only to `$VICTROLA_HOST` port 80.
- `scripts/capture_fixtures.py <host> <outdir>` — records and sanitizes real device
  payloads into `tests/fixtures/`.

## Plan

The implementation plan lives at `docs/superpowers/plans/2026-10-03-victrola-stream-ha.md`.
Read its **Now** section first at the start of a session; it carries the current step,
the next step, and open questions.

## Rules

- Read `gotchas.md` first, every session.
- Every write to a value node is typed and confirmed by reading it back. A mismatch
  raises; there is no optimistic state.
- Never port-scan. Talk only to the configured host and the stream URLs it returns.
- Fixtures are sanitized real captures — no real serial, MAC, SSID, BSSID, Sonos RINCON
  id, Sonos household id, or room names.
- Never cache a stream URL across a reconnect. Read it fresh after every (re)connect.
