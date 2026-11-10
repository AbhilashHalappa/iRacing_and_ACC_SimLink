# ACC Downstream Fan-out Queues

**Status:** Implemented on \`feature/acquisition-foundation\`; fan-out live validation passed. Required-consumer failure policy and fault-injection tests are implemented; validation is pending.

## Purpose

The acquisition ring buffer remains single-producer/single-consumer (SPSC).
A dispatcher consumes that source queue downstream of acquisition and offers
each immutable snapshot independently to one bounded queue per registered
consumer. Consumers never share a queue and cannot remove another consumer's
samples.

The Physics recording validation script now uses this fan-out path for its
required recorder consumer. The same interface supports additional independent
decoder, analysis, diagnostics, and test consumers without changing the
acquisition worker.

## Thread and ownership boundary

1. The Physics acquisition worker publishes to its existing SPSC ring buffer.
   It does not know about registered consumers and performs no fan-out work.
2. One dispatcher thread consumes the acquisition queue.
3. For each source sample, the dispatcher attempts a nonblocking offer to
   every registered consumer queue, independently.
4. Each consumer owns its queue and its processing worker. A full queue rejects
   only that consumer's delivery; later consumers are still offered the sample.
5. A consumer acknowledges each dequeued sample only after its work has
   completed. For raw recording, acknowledgement occurs only after the
   containing batch write, flush, and \`fsync\` succeed.

The fan-out layer passes references to immutable snapshots; it does not copy
or decode the raw payload. It is entirely downstream of the 480 Hz acquisition
loop.

## Registration and lifecycle

Consumers are registered before \`FanOutDispatcher.run()\`. Each registration
requires a unique non-empty name and a positive queue capacity. Late
registration and repeated dispatcher start are rejected.

When stop is requested, the dispatcher continues until the source acquisition
queue is empty, then closes dispatch to all consumer queues. Closing dispatch
does not discard already accepted items: each consumer worker can drain its
queue. The consumer worker is stopped only after dispatcher drain completes.

If a consumer worker fails, it calls \`mark_failed(reason)\`. Its queued and
in-flight samples are accounted as failed, and future offers to that consumer
are rejected. Other consumer queues remain usable. If the dispatcher itself
fails, all consumers are marked failed so no queued work is silently reported
as processed.

## Accounting contract

For each consumer, counters have these meanings:

- **offered:** every source sample considered for this consumer.
- **dispatched:** samples successfully inserted into this consumer's queue.
- **rejected:** samples not accepted because the queue was full, closed, or
  failed. First and last lost capture sequence are retained.
- **processed:** samples explicitly acknowledged after successful processing.
- **failed:** dispatched samples whose processing failed, including queued or
  in-flight samples explicitly failed when the consumer shuts down abnormally.
- **pending:** queued samples plus dequeued but not yet acknowledged in-flight
  samples.
- **high-water mark:** maximum outstanding depth observed (queued plus in-flight).

The per-consumer invariants are:

\`offered = dispatched + rejected\`

\`dispatched = processed + failed + pending\`

Dequeue is not processing. A recorder batch is acknowledged as processed only
after the writer confirms the durable batch boundary. Failed batches and
unprocessed queued samples cannot be counted as persisted.

The dispatcher separately reports source samples dequeued, source samples
dispatched to all consumer offers, required-consumer delivery rejections, and
the sequence currently in fan-out. The acquisition source queue retains its
own rejection and lost-sequence counters.

A consumer registered with \`required=True\` (the Physics recorder) contributes
to required-delivery rejection metrics. Any required recorder rejection,
processing failure, remaining pending sample, writer error, or recovery
mismatch causes the Physics recording validation script to report failure.
Loss is never converted into a successful recording result.


## Required versus optional consumer policy

A consumer's required flag is a delivery contract, not a scheduling priority.
All consumers remain bounded and nonblocking from the dispatcher's perspective.

| Event | Required raw recorder | Optional/best-effort consumer |
|---|---|---|
| Queue full / offer rejected | Count rejection and lost sequence; recording is incomplete | Count rejection and lost sequence for that consumer only |
| Worker exception / crash | Mark the consumer failed; account queued and in-flight samples as failed; recording is incomplete | Mark that consumer failed and account its outstanding samples; other consumers continue |
| Processing error | Acknowledge the affected sample as failed, never processed; recording is incomplete | Acknowledge the affected sample as failed; other consumers continue |
| Shutdown drain | Drain source first, close dispatch, then drain accepted recorder work and acknowledge only after durable writes | Drain accepted work if its worker is healthy; otherwise explicitly fail its outstanding work |
| Shutdown timeout | Mark the run incomplete; do not claim recovery or completion while a producer, dispatcher, or writer may still mutate the file | Report the consumer as timed out/failed; do not block required recording indefinitely |

There are no automatic retries in this layer. Retrying an arbitrary processing
operation can reorder samples or duplicate side effects; a future retry policy
must be consumer-specific, bounded, and idempotent. A transient exception is
therefore treated as a failed delivery for that sample. The raw recorder worker
fails its current batch and marks its remaining queued/in-flight deliveries
failed when its writer exits abnormally.

A required-recorder failure does not block the acquisition polling loop and
does not silently drop into a successful state. The current recording runner
continues only as far as its bounded shutdown sequence permits, then reports
status `failed` (incomplete) if any required delivery was rejected/failed,
any sample remains pending, any worker times out, any stage reports an error,
or recovery/checkpoint validation fails. On a shutdown timeout, recovery is
skipped while a producer, dispatcher, or recorder thread is still alive so the
validator does not scan or truncate a file concurrently with its writer.

Optional consumer failures are isolated: they do not increment required-delivery
losses and do not affect the raw recorder completion decision. They remain
visible in that optional consumer's own counters and error state. The recording
completion decision evaluates the required recorder only; it does not require
best-effort analysis to succeed.

## Sequence accounting and final status

For every consumer, the queue-level invariants are:

- `offered = dispatched + rejected`
- `dispatched = processed + failed + pending`
- `pending = queued + in_flight`

For the current single-required-recorder Physics path, end-to-end accounting is:

`acquired = persisted + acquisition_rejections + recorder_rejections + recorder_failed + acquisition_pending + recorder_pending + dispatcher_in_flight`

The final recording decision additionally requires:
- The registered recorder is marked required.
- Recorder processed acknowledgements equal persisted snapshots. Acknowledgement
  occurs only after the block write, flush, and `fsync` return successfully.
- No required-recorder rejection, failure, pending item, or in-flight item.
- No acquisition rejection or pending acquisition item; no dispatcher in-flight
  sample or dispatcher error.
- Zero end-to-end reconciliation delta.
- No producer, recorder, or shutdown error; no timed-out worker.
- Successful recovery/CRC validation with recovered count equal to persisted
  count and no invalid tail, plus a successful checkpoint worker.

The recording validator now uses a dedicated completion-policy function and
writes machine-readable `completion_failure_reasons` into its report. A run
with any failure reason is incomplete, even if a valid prefix of the raw file
can be recovered. Recovery is a salvage mechanism, not proof that the requested
recording completed.

Fault-injection coverage includes full required queues, optional consumer
failure isolation, required consumer crashes, failed recorder acknowledgements
(simulated write failure), shutdown timeout, and recovery/checkpoint failure.

## Memory bounds

Every consumer queue is a fixed-capacity ring of references. If consumer
capacities are \(C_1, C_2, \ldots, C_n\), the consumer queues retain at most
\(\sum_i C_i\) outstanding snapshot references in total. Each consumer's
capacity includes both queued and in-flight items; dequeueing does not free
capacity until that item is acknowledged or failed. The dispatcher itself
holds at most one additional source item while offering it to the consumers.

The snapshots and their immutable payload bytes are shared by reference
between consumer queues; fan-out does not allocate a second payload copy for
each consumer. The source acquisition ring is separately bounded by its own
configured capacity. Actual Python object and list-slot overhead is
interpreter/platform dependent, so this document defines a count bound rather
than claiming an unsupported exact byte count.

Capacity must be selected for each consumer's expected service latency and
maximum tolerated backlog. A slow optional decoder may reject its own samples
without affecting a required recorder queue. A required recorder queue must
be sized and monitored so any overflow is surfaced as a failed recording.

## Validation

Synthetic tests cover independent recorder/decoder-test delivery, queue
isolation, slow/full consumer behavior, failed consumer isolation, explicit
processing failure, required consumer loss, shutdown drain, and recorder
acknowledgement only after successful persistence. Live Physics recording
validation is required after the synthetic suite passes; the existing 600
second acquisition parity benchmark remains the performance reference and
must not be weakened.

## Capacity rationale

Configured queue capacities, stream-rate coverage, raw-payload memory bounds, measured Graphics slow-recorder results, and outstanding sizing assumptions are documented in [ACC Buffer Capacity Rationale](ACC_BUFFER_CAPACITY.md). The documented decision is to retain current defaults until stream-specific stall objectives and the remaining Physics/Static stress measurements are available.
