<?php

declare(strict_types=1);

namespace App\Logging\DTO;

/**
 * Result of sanitizing a payload for safe logging.
 *
 * Contains the sanitized data (with sensitive fields redacted and long strings
 * truncated) and metadata about the sanitization process.
 */
final readonly class SanitizationResult
{
    public function __construct(
        /** @var mixed The sanitized data payload (sensitive values redacted, long strings truncated) */
        public mixed $data,
        /** @var CaptureMeta Metadata describing what happened during sanitization */
        public CaptureMeta $captureMeta,
    ) {
    }

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(array $data): self
    {
        return new self(
            data: $data['data'] ?? null,
            captureMeta: CaptureMeta::fromArray(\is_array($data['capture_meta'] ?? null) ? $data['capture_meta'] : []),
        );
    }

    /**
     * @return array{data: mixed, capture_meta: array<string, bool|int>}
     */
    public function toArray(): array
    {
        return [
            'data' => $this->data,
            'capture_meta' => $this->captureMeta->toArray(),
        ];
    }
}
