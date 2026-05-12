-- One-time / idempotent backfill: align event_sequences with existing event_log rows.
-- Run after schema.sql has created event_sequences (FIX-068) on clusters that already
-- had events before the counter table existed; otherwise the first append may reuse
-- low event_seq values and hit UNIQUE (namespace_id, event_seq, occurred_at).
INSERT INTO event_sequences (namespace_id, seq)
SELECT namespace_id, MAX(event_seq)::bigint
FROM   event_log
GROUP BY namespace_id
ON CONFLICT (namespace_id) DO UPDATE
SET seq = GREATEST(event_sequences.seq, EXCLUDED.seq);
