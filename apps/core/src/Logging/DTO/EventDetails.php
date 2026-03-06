<?php

declare(strict_types=1);

namespace App\Logging\DTO;

/**
 * Detailed payload of a trace sequence event.
 *
 * Contains captured request/response data, sanitization metadata,
 * error information, and HTTP details for a single step in the trace.
 */
final readonly class EventDetails
{
    public function __construct(
        /** @var mixed|null Captured HTTP request headers (sanitized) */
        public mixed $headers = null,
        /** @var mixed|null Captured step input payload (sanitized) */
        public mixed $input = null,
        /** @var mixed|null Captured step output payload (sanitized) */
        public mixed $output = null,
        /** @var CaptureMeta|null Metadata about how payloads were sanitized */
        public ?CaptureMeta $captureMeta = null,
        /** @var string|null Application-specific error code (e.g. "connection_failed") */
        public ?string $errorCode = null,
        /** @var int|null HTTP response status code from the downstream call */
        public ?int $httpStatusCode = null,
        /** @var string|null Async task identifier from the A2A response */
        public ?string $taskId = null,
        /** @var mixed|null Exception data if an error occurred during processing */
        public mixed $exception = null,
    ) {
    }

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(array $data): self
    {
        return new self(
            headers: $data['headers'] ?? null,
            input: $data['input'] ?? null,
            output: $data['output'] ?? null,
            captureMeta: isset($data['capture_meta']) && \is_array($data['capture_meta'])
                ? CaptureMeta::fromArray($data['capture_meta'])
                : null,
            errorCode: isset($data['error_code']) ? (string) $data['error_code'] : null,
            httpStatusCode: isset($data['http_status_code']) ? (int) $data['http_status_code'] : null,
            taskId: isset($data['task_id']) ? (string) $data['task_id'] : null,
            exception: $data['exception'] ?? null,
        );
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        return [
            'headers' => $this->headers,
            'input' => $this->input,
            'output' => $this->output,
            'capture_meta' => $this->captureMeta?->toArray(),
            'error_code' => $this->errorCode,
            'http_status_code' => $this->httpStatusCode,
            'task_id' => $this->taskId,
            'exception' => $this->exception,
        ];
    }
}
