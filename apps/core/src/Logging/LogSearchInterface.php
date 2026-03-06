<?php

declare(strict_types=1);

namespace App\Logging;

interface LogSearchInterface
{
    /**
     * @param array<string, mixed> $searchBody
     *
     * @return array<string, mixed>|null
     */
    public function search(array $searchBody): ?array;
}
