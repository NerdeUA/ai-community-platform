<?php

declare(strict_types=1);

namespace App\LLM;

final class LiteLlmClient
{
    private const TIMEOUT = 60;

    public function __construct(
        private readonly string $baseUrl,
        private readonly string $apiKey,
        private readonly string $model,
    ) {
    }

    /**
     * @param list<array<string, mixed>> $messages
     * @param list<array<string, mixed>> $tools
     *
     * @return array<string, mixed>
     */
    public function chatCompletion(array $messages, array $tools = []): array
    {
        $body = [
            'model' => $this->model,
            'messages' => $messages,
            'max_tokens' => 4096,
        ];

        if ([] !== $tools) {
            $body['tools'] = $tools;
            $body['tool_choice'] = 'auto';
        }

        $json = json_encode($body, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);

        $headers = [
            'Content-Type: application/json',
            'Authorization: Bearer '.$this->apiKey,
            'Content-Length: '.strlen($json),
        ];

        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => implode("\r\n", $headers)."\r\n",
                'content' => $json,
                'timeout' => self::TIMEOUT,
                'ignore_errors' => true,
            ],
        ]);

        $endpoint = rtrim($this->baseUrl, '/').'/v1/chat/completions';

        set_error_handler(static fn (): bool => true);

        try {
            $result = file_get_contents($endpoint, false, $context);
        } finally {
            restore_error_handler();
        }

        if (false === $result) {
            throw new \RuntimeException('LiteLLM request failed: could not connect to '.$endpoint);
        }

        // Sanitize potentially malformed UTF-8 from LLM response
        $result = mb_convert_encoding($result, 'UTF-8', 'UTF-8');

        /** @var array<string, mixed> $data */
        $data = json_decode($result, true, 512, JSON_THROW_ON_ERROR);

        return $data;
    }
}
