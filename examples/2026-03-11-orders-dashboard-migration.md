---
type: session-checkpoint
updated: 2026-03-11
---

# Checkpoint — orders dashboard on the new warehouse

Read this file in full before doing anything else. Written for a reader
with zero context; every path and command below is exact.

## Objective

Move the internal orders dashboard off the legacy MySQL read-replica and
onto the Postgres warehouse, without the finance team noticing anything
except that the page loads faster. Cutover target is 2026-03-20.

## State

**Query layer — done, verified.** `api/queries/orders.py` now reads from
Postgres through `warehouse.session()`. All eleven dashboard queries are
ported. `python -m pytest tests/test_orders_queries.py` is green (11
passed, 0.9s) against the seeded fixture database in
`tests/fixtures/warehouse.sql`.

**Revenue totals — in flight, and wrong by a known amount.** The
warehouse `orders` table stores amounts in minor units (integer cents),
the legacy replica stored them as `DECIMAL(10,2)`. `api/queries/
orders.py:revenue_by_day` divides by 100; `revenue_by_channel` does not
yet, so the channel chart currently shows 100x the real numbers. Fix is
one line, not yet written.

**Refund rows — blocked.** The warehouse has no `refunds` table; the
loader team owns it and their ticket DATA-412 is scheduled for
2026-03-16. Until it lands the refunds panel reads the legacy replica
through the old client, which is why `api/legacy_client.py` is still
imported in `api/dashboard.py`.

**Front end — not started.** No changes needed unless the response shape
moves, and it has not.

## Decisions and why

**Cents everywhere in the API layer, formatting only in the front end.**
Considered converting to decimals at the query boundary so nothing
downstream changes. Rejected: the warehouse is the long-term source of
truth for three other consumers, and every one of them would then need
its own rounding rule. One conversion point in `web/src/format.ts` is
auditable; four scattered ones drift. This is why the `revenue_by_day`
fix divides in the serializer and not in SQL.

**No dual-write, no shadow period.** The replica is read-only for us and
finance reconciles monthly, so a bad day is recoverable from the
warehouse itself. A shadow-compare harness was priced at roughly two
days of work and rejected as more machinery than the risk justifies.

**Keep `api/legacy_client.py` until DATA-412 ships.** Deleting it now
would mean stubbing refunds, and a stubbed panel that silently shows
zeros is worse than an honest slow one.

## Open threads

1. Divide by 100 in `revenue_by_channel` (`api/queries/orders.py`, around
   line 140) and extend `tests/test_orders_queries.py` with a channel
   case asserting an exact figure, not a shape.
2. Re-run `scripts/compare_totals.py --date 2026-03-09` and confirm the
   warehouse and replica agree to the cent for a full day.
3. After DATA-412 lands on 2026-03-16: port the refunds panel, then
   delete `api/legacy_client.py` and its import in `api/dashboard.py`.
4. Ask the finance lead whether the channel chart should include
   cancelled orders. The legacy query excluded them, the ported query
   keeps that behavior, and nobody has confirmed it was intentional.

## Gotchas and dead ends

**Do not use `warehouse.session()` inside a request handler.** It opens
its own transaction and the dashboard's connection pool (size 5) empties
under the eleven parallel panel fetches; the page then hangs for exactly
30 seconds and returns a 504 with no traceback. Two hours went into
chasing this as a query-performance problem before the pool turned out
to be the cause. Handlers take the session from `api/deps.py:get_db`.

**`pytest -k revenue` alone passes even when the code is wrong.** The
revenue fixtures happen to use round-dollar amounts, so a missing
divide-by-100 still matches on the day-level assertion. Run the whole
file, and assert exact cent values in any new case.

**The staging warehouse lags production by up to six hours.** A number
that disagrees with the dashboard is not automatically a bug. Check
`SELECT max(loaded_at) FROM warehouse.orders` before investigating.
