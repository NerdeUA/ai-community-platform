<?php

declare(strict_types=1);

namespace App\Logging\DTO;

/**
 * A projected trace event in a sequence diagram.
 *
 * Represents a single step in a distributed trace, capturing the interaction
 * between two participants (source and target) with timing and payload details.
 */
final readonly class SequenceEvent
{
    public function __construct(
        /** @var string Unique event identifier (timestamp + index) */
        public string $id,
        /** @var string Structured event name (e.g. "core.a2a.outbound.started") */
        public string $eventName,
        /** @var string Processing step category (e.g. "a2a_outbound", "llm_call") */
        public string $step,
        /** @var string Operation being performed (tool name, intent, or step name) */
        public string $operation,
        /** @var string Source participant that initiated this step */
        public string $from,
        /** @var string Target participant receiving the request */
        public string $to,
        /** @var string Current status of this step (started, completed, failed) */
        public string $status,
        /** @var int Duration of this step in milliseconds */
        public int $durationMs = 0,
        /** @var string ISO 8601 timestamp of when this event occurred */
        public string $timestamp = '',
        /** @var string Distributed trace identifier linking all events in the trace */
        public string $traceId = '',
        /** @var string Request identifier for this specific request within the trace */
        public string $requestId = '',
        /** @var EventDetails Detailed payload data for this event */
        public EventDetails $details = new EventDetails(),
    ) {
    }

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(array $data): self
    {
        return new self(
            id: (string) ($data['id'] ?? ''),
            eventName: (string) ($data['event_name'] ?? ''),
            step: (string) ($data['step'] ?? ''),
            operation: (string) ($data['operation'] ?? ''),
            from: (string) ($data['from'] ?? ''),
            to: (string) ($data['to'] ?? ''),
            status: (string) ($data['status'] ?? ''),
            durationMs: (int) ($data['duration_ms'] ?? 0),
            timestamp: (string) ($data['timestamp'] ?? ''),
            traceId: (string) ($data['trace_id'] ?? ''),
            requestId: (string) ($data['request_id'] ?? ''),
            details: EventDetails::fromArray(\is_array($data['details'] ?? null) ? $data['details'] : []),
        );
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        return [
            'id' => $this->id,
            'event_name' => $this->eventName,
            'step' => $this->step,
            'operation' => $this->operation,
            'from' => $this->from,
            'to' => $this->to,
            'status' => $this->status,
            'duration_ms' => $this->durationMs,
            'timestamp' => $this->timestamp,
            'trace_id' => $this->traceId,
            'request_id' => $this->requestId,
            'details' => $this->details->toArray(),
        ];
    }
}
