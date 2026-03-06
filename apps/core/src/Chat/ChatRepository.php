<?php

declare(strict_types=1);

namespace App\Chat;

use App\Chat\DTO\ChatListItem;
use App\Chat\DTO\ChatMessage;
use App\Logging\LogSearchInterface;
use Doctrine\DBAL\Connection;

final class ChatRepository
{
    private const PAGE_SIZE = 20;

    public function __construct(
        private readonly Connection $connection,
        private readonly LogSearchInterface $indexManager,
    ) {
    }

    /**
     * @return list<ChatListItem>
     */
    public function listChats(int $page = 1, string $agent = '', string $status = ''): array
    {
        $where = '';
        $params = [];

        if ('' !== $agent) {
            $where .= ' AND agent = :agent';
            $params['agent'] = $agent;
        }
        if ('' !== $status) {
            $where .= ' AND status = :status';
            $params['status'] = $status;
        }

        $offset = ($page - 1) * self::PAGE_SIZE;

        $sql = <<<SQL
            SELECT
                trace_id,
                agent,
                skill,
                status,
                MAX(duration_ms) AS duration_ms,
                MIN(created_at) AS first_at,
                MAX(created_at) AS last_at,
                COUNT(*) AS message_count
            FROM a2a_message_audit
            WHERE 1=1 {$where}
            GROUP BY trace_id, agent, skill, status
            ORDER BY MAX(created_at) DESC
            LIMIT :limit OFFSET :offset
        SQL;

        /** @var list<array<string, mixed>> $rows */
        $rows = $this->connection->fetchAllAssociative($sql, array_merge($params, [
            'limit' => self::PAGE_SIZE,
            'offset' => $offset,
        ]));

        $items = [];
        foreach ($rows as $row) {
            $items[] = new ChatListItem(
                sessionKey: (string) $row['trace_id'],
                channel: 'openclaw',
                sender: (string) ($row['agent'] ?? 'unknown'),
                messageCount: (int) $row['message_count'],
                lastMessageAt: (string) $row['last_at'],
                firstMessageAt: (string) $row['first_at'],
                traceIds: [(string) $row['trace_id']],
                agent: isset($row['agent']) ? (string) $row['agent'] : null,
                skill: isset($row['skill']) ? (string) $row['skill'] : null,
                status: isset($row['status']) ? (string) $row['status'] : null,
                durationMs: isset($row['duration_ms']) ? (int) $row['duration_ms'] : null,
            );
        }

        return $items;
    }

    public function countChats(string $agent = '', string $status = ''): int
    {
        $where = '';
        $params = [];

        if ('' !== $agent) {
            $where .= ' AND agent = :agent';
            $params['agent'] = $agent;
        }
        if ('' !== $status) {
            $where .= ' AND status = :status';
            $params['status'] = $status;
        }

        $sql = <<<SQL
            SELECT COUNT(DISTINCT trace_id) AS cnt
            FROM a2a_message_audit
            WHERE 1=1 {$where}
        SQL;

        return (int) $this->connection->fetchOne($sql, $params);
    }

    /**
     * Get chat detail by trace_id: audit rows + OpenSearch enrichment.
     *
     * @return list<ChatMessage>
     */
    public function getChatMessages(string $traceId): array
    {
        $messages = $this->getMessagesFromOpenSearch($traceId);

        if ([] === $messages) {
            $messages = $this->getMessagesFromAudit($traceId);
        }

        return $messages;
    }

    /**
     * @return list<string>
     */
    public function getTraceIdsForChat(string $traceId): array
    {
        return [$traceId];
    }

    public static function pageSize(): int
    {
        return self::PAGE_SIZE;
    }

    /**
     * @return list<ChatMessage>
     */
    private function getMessagesFromOpenSearch(string $traceId): array
    {
        $searchBody = [
            'query' => [
                'bool' => [
                    'filter' => [
                        ['term' => ['trace_id' => $traceId]],
                    ],
                ],
            ],
            'sort' => [['@timestamp' => 'asc']],
            'size' => 500,
        ];

        $result = $this->indexManager->search($searchBody);
        if (null === $result) {
            return [];
        }

        /** @var list<array{_source: array<string, mixed>}> $rawHits */
        $rawHits = $result['hits']['hits'] ?? [];
        if ([] === $rawHits) {
            return [];
        }

        $messages = [];
        foreach ($rawHits as $hit) {
            $source = $hit['_source'];
            $eventName = (string) ($source['event_name'] ?? '');

            if ('' === $eventName) {
                continue;
            }

            $direction = match (true) {
                str_contains($eventName, 'received') => 'inbound',
                str_contains($eventName, '.invoke.') && str_contains($eventName, 'started') => 'tool_call',
                str_contains($eventName, '.invoke.') && str_contains($eventName, 'completed') => 'tool_result',
                str_contains($eventName, '.invoke.') && str_contains($eventName, 'failed') => 'tool_error',
                str_contains($eventName, '.tool.execute.started') => 'tool_call',
                str_contains($eventName, '.tool.execute.completed') => 'tool_result',
                str_contains($eventName, '.tool.execute.failed') => 'tool_error',
                str_contains($eventName, 'a2a.outbound.started') => 'tool_call',
                str_contains($eventName, 'a2a.outbound.completed') => 'tool_result',
                str_contains($eventName, 'sent') => 'outbound',
                default => 'event',
            };

            /** @var array<string, mixed> $context */
            $context = (array) ($source['context'] ?? []);

            /** @var array<string, mixed> $stepInput */
            $stepInput = (array) ($context['step_input'] ?? $source['step_input'] ?? []);
            /** @var array<string, mixed> $stepOutput */
            $stepOutput = (array) ($context['step_output'] ?? $source['step_output'] ?? []);

            $payload = match ($direction) {
                'inbound', 'tool_call' => $stepInput,
                'outbound', 'tool_result', 'tool_error' => $stepOutput,
                default => [],
            };

            $tool = $source['tool'] ?? $source['intent'] ?? $context['tool'] ?? $context['intent'] ?? null;

            $messages[] = new ChatMessage(
                direction: $direction,
                timestamp: (string) ($source['@timestamp'] ?? ''),
                eventName: $eventName,
                traceId: isset($source['trace_id']) ? (string) $source['trace_id'] : null,
                sender: isset($source['sender']) ? (string) $source['sender'] : (isset($source['source_app']) ? (string) $source['source_app'] : null),
                recipient: isset($source['recipient']) ? (string) $source['recipient'] : (isset($source['target_app']) ? (string) $source['target_app'] : null),
                tool: null !== $tool ? (string) $tool : null,
                status: isset($source['status']) ? (string) $source['status'] : null,
                durationMs: isset($source['duration_ms']) ? (int) $source['duration_ms'] : null,
                payload: $payload,
            );
        }

        return $messages;
    }

    /**
     * Fallback: build messages from a2a_message_audit when OpenSearch has no data.
     *
     * @return list<ChatMessage>
     */
    private function getMessagesFromAudit(string $traceId): array
    {
        $sql = <<<'SQL'
            SELECT skill, agent, trace_id, request_id, status, duration_ms,
                   http_status_code, error_code, actor, created_at
            FROM a2a_message_audit
            WHERE trace_id = :trace_id
            ORDER BY created_at ASC
        SQL;

        /** @var list<array<string, mixed>> $rows */
        $rows = $this->connection->fetchAllAssociative($sql, ['trace_id' => $traceId]);

        $messages = [];
        foreach ($rows as $row) {
            $messages[] = new ChatMessage(
                direction: 'tool_call',
                timestamp: (string) $row['created_at'],
                eventName: 'a2a.audit',
                traceId: (string) $row['trace_id'],
                sender: (string) ($row['actor'] ?? 'openclaw'),
                recipient: (string) ($row['agent'] ?? 'unknown'),
                tool: (string) ($row['skill'] ?? ''),
                status: (string) ($row['status'] ?? ''),
                durationMs: isset($row['duration_ms']) ? (int) $row['duration_ms'] : null,
                payload: array_filter([
                    'http_status_code' => $row['http_status_code'] ?? null,
                    'error_code' => $row['error_code'] ?? null,
                    'request_id' => $row['request_id'] ?? null,
                ]),
            );
        }

        return $messages;
    }
}
