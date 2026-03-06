<?php

declare(strict_types=1);

namespace App\Chat\DTO;

final readonly class ChatMessage
{
    /**
     * @param array<string, mixed> $payload
     */
    public function __construct(
        public string $direction,
        public string $timestamp,
        public string $eventName,
        public ?string $traceId,
        public ?string $sender,
        public ?string $recipient,
        public ?string $tool,
        public ?string $status,
        public ?int $durationMs,
        public array $payload,
    ) {
    }
}
