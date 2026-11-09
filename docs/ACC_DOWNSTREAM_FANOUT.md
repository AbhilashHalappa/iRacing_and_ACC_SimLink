# ACC Downstream Fan-out Queues

**Status:** Implemented on \`feature/acquisition-foundation\`; synthetic validation pending.

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

## Memory bounds

Every consumer queue is a fixed-capacity ring of references. If consumer
capacities are \(C_1, C_2, \ldots, C_n\), the fan-out layer retains at most
\(\sum_i C_i\) queued snapshot references, plus the currently in-flight item
per consumer and bounded bookkeeping entries for those in-flight items.

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
