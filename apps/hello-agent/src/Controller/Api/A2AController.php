<?php

declare(strict_types=1);

namespace App\Controller\Api;

use App\A2A\HelloA2AHandler;
use App\Observability\LangfuseIngestionClient;
use Psr\Log\LoggerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

final class A2AController extends AbstractController
{
    public function __construct(
        private readonly HelloA2AHandler $handler,
        private readonly LangfuseIngestionClient $langfuse,
        private readonly LoggerInterface $logger,
    ) {
    }

    #[Route('/api/v1/a2a', name: 'api_a2a', methods: ['POST'])]
    public function __invoke(Request $request): JsonResponse
    {
        /** @var array<string, mixed>|null $data */
        $data = json_decode($request->getContent(), true);

        if (!\is_array($data) || !isset($data['intent'])) {
            $this->logger->warning('Invalid A2A payload received', [
                'ip' => $request->getClientIp(),
            ]);

            return $this->json(
                ['error' => 'Invalid A2A payload: intent is required'],
                Response::HTTP_UNPROCESSABLE_ENTITY,
            );
        }

        $traceId = (string) ($data['trace_id'] ?? uniqid('trace_', true));
        $requestId = (string) ($data['request_id'] ?? uniqid('req_', true));
        $intent = (string) ($data['intent'] ?? 'unknown');
        $data['trace_id'] = $traceId;
        $data['request_id'] = $requestId;

        $this->logger->info('A2A request received', [
            'intent' => $intent,
            'trace_id' => $traceId,
            'request_id' => $requestId,
        ]);

        $start = microtime(true);

        $result = $this->handler->handle($data);
        $durationMs = (int) ((microtime(true) - $start) * 1000);
        $this->langfuse->recordA2ARequest($traceId, $requestId, $intent, (array) ($data['payload'] ?? []), $result, $durationMs);

        $status = (string) ($result['status'] ?? 'unknown');
        $this->logger->info('A2A request completed', [
            'intent' => $intent,
            'status' => $status,
            'duration_ms' => $durationMs,
            'trace_id' => $traceId,
            'request_id' => $requestId,
        ]);

        return $this->json($result);
    }
}
