<?php

declare(strict_types=1);

namespace App\Controller\Api;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

final class ManifestController extends AbstractController
{
    #[Route('/api/v1/manifest', name: 'api_manifest', methods: ['GET'])]
    public function __invoke(): JsonResponse
    {
        return $this->json([
            'name' => 'hello-agent',
            'version' => '1.0.0',
            'description' => 'Simple hello-world reference agent',
            'permissions' => [],
            'commands' => ['/hello'],
            'events' => [],
            'capabilities' => ['hello.greet'],
            'capability_schemas' => [
                'hello.greet' => [
                    'description' => 'Greet a user by name. Returns a friendly hello message.',
                    'input_schema' => [
                        'type' => 'object',
                        'properties' => [
                            'name' => [
                                'type' => 'string',
                                'description' => 'Name of the person to greet',
                            ],
                        ],
                    ],
                ],
            ],
            'a2a_endpoint' => 'http://hello-agent/api/v1/a2a',
            'health_url' => 'http://hello-agent/health',
        ]);
    }
}
