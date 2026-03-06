<?php

declare(strict_types=1);

namespace App\Chat\DTO;

final readonly class ChatListItem
{
    /**
     * @param list<string> $traceIds
     */
    public function __construct(
        public string $sessionKey,
        public string $channel,
        public string $sender,
        public int $messageCount,
        public string $lastMessageAt,
        public string $firstMessageAt,
        public array $traceIds,
        public ?string $agent = null,
        public ?string $skill = null,
        public ?string $status = null,
        public ?int $durationMs = null,
    ) {
    }
}
