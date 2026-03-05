<?php

declare(strict_types=1);

namespace App\Tests\Unit\A2A;

use App\A2A\HelloA2AHandler;
use Codeception\Test\Unit;
use PHPUnit\Framework\MockObject\MockObject;
use Psr\Log\LoggerInterface;

final class HelloA2AHandlerTest extends Unit
{
    private LoggerInterface&MockObject $logger;

    protected function setUp(): void
    {
        $this->logger = $this->createMock(LoggerInterface::class);
    }

    public function testGreetWithoutApiKeyReturnsFallback(): void
    {
        $handler = new HelloA2AHandler($this->logger, 'http://litellm:4000', '', 'minimax/minimax-m2.5');

        $result = $handler->handle([
            'intent' => 'hello.greet',
            'payload' => [],
        ]);

        $this->assertSame('completed', $result['status']);
        $this->assertSame('Hello, World!', $result['result']['greeting']);
    }

    public function testGreetWithCustomName(): void
    {
        $handler = new HelloA2AHandler($this->logger, 'http://litellm:4000', '', 'minimax/minimax-m2.5');

        $result = $handler->handle([
            'intent' => 'hello.greet',
            'payload' => ['name' => 'Dimas'],
        ]);

        $this->assertSame('completed', $result['status']);
        $this->assertSame('Hello, Dimas!', $result['result']['greeting']);
    }

    public function testUnknownIntentReturnsFailed(): void
    {
        $handler = new HelloA2AHandler($this->logger, 'http://litellm:4000', '', 'minimax/minimax-m2.5');

        $result = $handler->handle([
            'intent' => 'unknown.action',
            'request_id' => 'req-123',
        ]);

        $this->assertSame('failed', $result['status']);
        $this->assertSame('req-123', $result['request_id']);
        $this->assertStringContainsString('Unknown intent', $result['error']);
    }

    public function testGreetPreservesRequestId(): void
    {
        $handler = new HelloA2AHandler($this->logger, 'http://litellm:4000', '', 'minimax/minimax-m2.5');

        $result = $handler->handle([
            'intent' => 'hello.greet',
            'request_id' => 'custom-req-id',
            'payload' => ['name' => 'Test'],
        ]);

        $this->assertSame('custom-req-id', $result['request_id']);
    }

    public function testGreetGeneratesRequestIdWhenMissing(): void
    {
        $handler = new HelloA2AHandler($this->logger, 'http://litellm:4000', '', 'minimax/minimax-m2.5');

        $result = $handler->handle([
            'intent' => 'hello.greet',
            'payload' => [],
        ]);

        $this->assertNotEmpty($result['request_id']);
        $this->assertStringStartsWith('a2a_', $result['request_id']);
    }

    public function testGreetWithUnicodeName(): void
    {
        $handler = new HelloA2AHandler($this->logger, 'http://litellm:4000', '', 'minimax/minimax-m2.5');

        $result = $handler->handle([
            'intent' => 'hello.greet',
            'payload' => ['name' => 'Дімас'],
        ]);

        $this->assertSame('Hello, Дімас!', $result['result']['greeting']);
    }
}
