<?php

declare(strict_types=1);

namespace App\A2A;

use Psr\Log\LoggerInterface;

final class HelloA2AHandler
{
    private const DEFAULT_SYSTEM_PROMPT = 'You are a friendly greeter. Respond with a warm, creative greeting.';

    public function __construct(
        private readonly LoggerInterface $logger,
        private readonly string $liteLlmBaseUrl,
        private readonly string $liteLlmApiKey,
        private readonly string $llmModel,
    ) {
    }

    /**
     * @param array<string, mixed> $request
     *
     * @return array<string, mixed>
     */
    public function handle(array $request): array
    {
        $intent = (string) ($request['intent'] ?? '');
        $requestId = (string) ($request['request_id'] ?? uniqid('a2a_', true));
        $traceId = (string) ($request['trace_id'] ?? '');
        $systemPrompt = (string) ($request['system_prompt'] ?? '');

        /** @var array<string, mixed> $payload */
        $payload = $request['payload'] ?? [];

        $logCtx = ['intent' => $intent, 'request_id' => $requestId, 'trace_id' => $traceId];

        return match ($intent) {
            'hello.greet' => $this->handleGreet($payload, $requestId, $systemPrompt, $logCtx),
            default => $this->handleUnknown($intent, $requestId, $logCtx),
        };
    }

    /**
     * @param array<string, mixed> $payload
     * @param array<string, mixed> $logCtx
     *
     * @return array<string, mixed>
     */
    private function handleGreet(array $payload, string $requestId, string $systemPrompt, array $logCtx): array
    {
        $name = (string) ($payload['name'] ?? 'World');

        $this->logger->info('Greeting requested', $logCtx + ['name' => $name]);

        $greeting = $this->generateGreeting($name, $systemPrompt, $logCtx);

        $this->logger->info('Greeting processed', $logCtx + [
            'name' => $name,
            'via_llm' => '' !== $this->liteLlmApiKey,
        ]);

        return [
            'status' => 'completed',
            'request_id' => $requestId,
            'result' => [
                'greeting' => $greeting,
            ],
        ];
    }

    /**
     * @param array<string, mixed> $logCtx
     *
     * @return array<string, mixed>
     */
    private function handleUnknown(string $intent, string $requestId, array $logCtx): array
    {
        $this->logger->warning('Unknown intent received', $logCtx);

        return [
            'status' => 'failed',
            'request_id' => $requestId,
            'error' => "Unknown intent: {$intent}",
        ];
    }

    /**
     * @param array<string, mixed> $logCtx
     */
    private function generateGreeting(string $name, string $systemPrompt, array $logCtx): string
    {
        if ('' === $this->liteLlmApiKey) {
            $this->logger->debug('No API key, using fallback greeting', $logCtx + ['name' => $name]);

            return "Hello, {$name}!";
        }

        $system = '' !== $systemPrompt ? $systemPrompt : self::DEFAULT_SYSTEM_PROMPT;

        $this->logger->debug('Calling LLM', $logCtx + [
            'model' => $this->llmModel,
            'has_custom_prompt' => '' !== $systemPrompt,
        ]);

        $start = microtime(true);

        try {
            $result = $this->callLlm($system, "Привітай користувача {$name}");
            $durationMs = (int) ((microtime(true) - $start) * 1000);

            $this->logger->info('LLM call succeeded', $logCtx + [
                'model' => $this->llmModel,
                'duration_ms' => $durationMs,
            ]);

            return $result;
        } catch (\Throwable $e) {
            $durationMs = (int) ((microtime(true) - $start) * 1000);

            $this->logger->warning('LLM call failed, using fallback', $logCtx + [
                'error' => $e->getMessage(),
                'model' => $this->llmModel,
                'duration_ms' => $durationMs,
            ]);

            return "Hello, {$name}!";
        }
    }

    private function callLlm(string $systemPrompt, string $userMessage): string
    {
        $body = json_encode([
            'model' => $this->llmModel,
            'messages' => [
                ['role' => 'system', 'content' => $systemPrompt],
                ['role' => 'user', 'content' => $userMessage],
            ],
            'max_tokens' => 200,
        ], \JSON_THROW_ON_ERROR);

        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => implode("\r\n", [
                    'Content-Type: application/json',
                    'Authorization: Bearer '.$this->liteLlmApiKey,
                    'Content-Length: '.strlen($body),
                ])."\r\n",
                'content' => $body,
                'timeout' => 25,
                'ignore_errors' => true,
            ],
        ]);

        $endpoint = rtrim($this->liteLlmBaseUrl, '/').'/v1/chat/completions';
        $result = @file_get_contents($endpoint, false, $context);

        if (false === $result) {
            throw new \RuntimeException('LiteLLM API request failed');
        }

        /** @var array{choices?: list<array{message?: array{content?: string}}>} $data */
        $data = json_decode($result, true, 512, \JSON_THROW_ON_ERROR);

        $content = (string) ($data['choices'][0]['message']['content'] ?? '');

        if ('' === $content) {
            throw new \RuntimeException('Empty LLM response');
        }

        return $content;
    }
}
