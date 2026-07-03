# C24

`@tags: concurrency-lock; uniqueness-enforcement; reasoning-shape; scope:diff`

**Pattern:** A poll-based producer enqueues one job per entity with a STABLE custom dedup key
(BullMQ `jobId: prefix:${entityId}`) AND retains failed jobs (`removeOnFail: <count>` or the BullMQ
default). BullMQ refuses to `add()` a job whose `jobId` exists in ANY retained state — so ONE transient
failure leaves a failed job occupying the key, and every future poll's `add()` is a silent no-op: that
entity never drains again until the failed job ages out or is manually cleared. Sibling trap: a
repeatable scheduler (`upsertJobScheduler(id, {every}, {name})`) with no template `opts` retains every
produced job → unbounded accumulation on a `noeviction` Redis → eventual OOM harming all queues.

**Check before dispatch:**
1. If the diff enqueues with a stable/custom `jobId` for dedup, confirm `removeOnFail: true` (not a
   retained count) so a failed job frees the key for the next poll to re-enqueue — plus `attempts` +
   `backoff` so a transient failure self-heals before removal. Ask: "if this job fails ONCE, does the
   key free up so the producer can re-enqueue?" If no → permanent silent wedge.
2. If the diff calls `upsertJobScheduler` / adds a repeatable/cron job, confirm the jobTemplate carries
   `opts: { removeOnComplete: true, removeOnFail: <bounded> }` — unbounded retention is a Redis leak.

**Design default:** For any dedup-key + failure-retention queue design, make failure free the key
(`removeOnFail: true` + attempts/backoff) and bound every repeatable scheduler's produced-job
retention — a retained failure or unbounded scheduler output is a silent durability/availability bug.
