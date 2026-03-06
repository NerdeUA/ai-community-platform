<?php

declare(strict_types=1);

namespace App\Logging;

final class TraceSequenceProjector
{
    /**
     * @param list<array<string, mixed>> $hits
     *
     * @return array{
     *   events: list<array<string, mixed>>,
     *   participants: list<string>,
     *   call_events: list<array<string, mixed>>,
     *   call_participants: list<string>
     * }
     */
    public function project(array $hits): array
    {
        $events = [];
        $participants = [];
        $callEvents = [];
        $callParticipants = [];

        foreach ($hits as $idx => $source) {
            $eventName = (string) ($source['event_name'] ?? '');
            $step = (string) ($source['step'] ?? '');
            $sourceApp = (string) ($source['source_app'] ?? $source['app_name'] ?? '');
            if ('' === $eventName || '' === $step || '' === $sourceApp) {
                continue;
            }

            $targetApp = (string) ($source['target_app'] ?? $sourceApp);
            /** @var array<string, mixed> $context */
            $context = is_array($source['context'] ?? null) ? $source['context'] : [];
            $operation = (string) ($source['tool'] ?? $source['intent'] ?? $step);
            $status = (string) ($source['status'] ?? strtolower((string) ($source['level_name'] ?? 'unknown')));
            $durationMs = (int) ($source['duration_ms'] ?? 0);

            $event = [
                'id' => sprintf('%s_%d', (string) ($source['@timestamp'] ?? 'evt'), $idx),
                'event_name' => $eventName,
                'step' => $step,
                'operation' => $operation,
                'from' => $sourceApp,
                'to' => $targetApp,
                'status' => $status,
                'duration_ms' => $durationMs,
                'timestamp' => (string) ($source['@timestamp'] ?? ''),
                'trace_id' => (string) ($source['trace_id'] ?? ''),
                'request_id' => (string) ($source['request_id'] ?? ''),
                'details' => [
                    'headers' => $context['request_headers'] ?? null,
                    'input' => $context['step_input'] ?? null,
                    'output' => $context['step_output'] ?? null,
                    'capture_meta' => $context['capture_meta'] ?? null,
                    'error_code' => $source['error_code'] ?? null,
                    'http_status_code' => $source['http_status_code'] ?? null,
                    'task_id' => $source['task_id'] ?? null,
                    'exception' => $source['exception'] ?? null,
                ],
            ];
            $events[] = $event;

            $participants[$sourceApp] = true;
            $participants[$targetApp] = true;

            if ($this->isCallStep($step)) {
                $callEvents[] = $event;
                $callParticipants[$sourceApp] = true;
                $callParticipants[$targetApp] = true;
            }
        }

        return [
            'events' => $events,
            'participants' => array_keys($participants),
            'call_events' => $callEvents,
            'call_participants' => array_keys($callParticipants),
        ];
    }

    private function isCallStep(string $step): bool
    {
        return in_array($step, ['a2a_outbound', 'a2a_inbound', 'llm_call', 'agent_card_fetch'], true);
    }
}
