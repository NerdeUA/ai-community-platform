<?php

declare(strict_types=1);

namespace App\Logging\DTO;

/**
 * Metadata about the payload sanitization process.
 *
 * Tracks whether truncation occurred, original vs captured sizes,
 * and how many fields were redacted or truncated during sanitization.
 */
final readonly class CaptureMeta
{
    public function __construct(
        /** @var bool Whether the payload was truncated due to exceeding the size limit */
        public bool $isTruncated = false,
        /** @var int Original payload size in bytes before any sanitization */
        public int $originalSizeBytes = 0,
        /** @var int Final payload size in bytes after sanitization */
        public int $capturedSizeBytes = 0,
        /** @var int Number of sensitive fields that were redacted (e.g. tokens, passwords) */
        public int $redactedFieldsCount = 0,
        /** @var int Number of string values that were truncated due to length limits */
        public int $truncatedValuesCount = 0,
    ) {
    }

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(array $data): self
    {
        return new self(
            isTruncated: (bool) ($data['is_truncated'] ?? false),
            originalSizeBytes: (int) ($data['original_size_bytes'] ?? 0),
            capturedSizeBytes: (int) ($data['captured_size_bytes'] ?? 0),
            redactedFieldsCount: (int) ($data['redacted_fields_count'] ?? 0),
            truncatedValuesCount: (int) ($data['truncated_values_count'] ?? 0),
        );
    }

    /**
     * @return array<string, bool|int>
     */
    public function toArray(): array
    {
        return [
            'is_truncated' => $this->isTruncated,
            'original_size_bytes' => $this->originalSizeBytes,
            'captured_size_bytes' => $this->capturedSizeBytes,
            'redacted_fields_count' => $this->redactedFieldsCount,
            'truncated_values_count' => $this->truncatedValuesCount,
        ];
    }
}
