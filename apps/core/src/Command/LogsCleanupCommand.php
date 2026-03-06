<?php

declare(strict_types=1);

namespace App\Command;

use App\Logging\LogIndexManager;
use Doctrine\DBAL\Connection;
use Symfony\Component\Console\Attribute\AsCommand;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;
use Symfony\Component\Console\Style\SymfonyStyle;

#[AsCommand(name: 'logs:cleanup', description: 'Delete old log indices and audit records based on retention policy')]
final class LogsCleanupCommand extends Command
{
    public function __construct(
        private readonly LogIndexManager $indexManager,
        private readonly Connection $connection,
        private readonly int $defaultRetentionDays,
        private readonly int $defaultMaxSizeGb,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this
            ->addOption('max-age', null, InputOption::VALUE_REQUIRED, 'Max age in days', (string) $this->defaultRetentionDays)
            ->addOption('max-size-gb', null, InputOption::VALUE_REQUIRED, 'Max total size in GB', (string) $this->defaultMaxSizeGb)
            ->addOption('dry-run', null, InputOption::VALUE_NONE, 'Show what would be deleted without deleting');
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $io = new SymfonyStyle($input, $output);

        $maxAge = (int) $input->getOption('max-age');
        $maxSizeGb = (int) $input->getOption('max-size-gb');
        $dryRun = (bool) $input->getOption('dry-run');

        if ($dryRun) {
            $io->note('DRY RUN — nothing will be deleted.');
        }

        $this->cleanupOpenSearchIndices($io, $maxAge, $maxSizeGb, $dryRun);
        $this->cleanupAuditRecords($io, $maxAge, $dryRun);

        return Command::SUCCESS;
    }

    private function cleanupOpenSearchIndices(SymfonyStyle $io, int $maxAge, int $maxSizeGb, bool $dryRun): void
    {
        $io->section('OpenSearch indices');

        $indices = $this->indexManager->listLogIndices();
        if ([] === $indices) {
            $io->success('No log indices found.');

            return;
        }

        $io->text(sprintf('Found %d log index(es).', \count($indices)));

        $cutoffDate = (new \DateTimeImmutable())->modify(sprintf('-%d days', $maxAge))->format('Y-m-d');
        $deleted = 0;

        foreach ($indices as $entry) {
            if ($entry['date'] < $cutoffDate) {
                $io->text(sprintf('  [age] %s (date: %s, before cutoff: %s)', $entry['index'], $entry['date'], $cutoffDate));

                if (!$dryRun) {
                    $this->indexManager->deleteIndex($entry['index']);
                }

                ++$deleted;
            }
        }

        $remaining = array_filter($indices, static fn (array $e): bool => $e['date'] >= $cutoffDate);
        $totalBytes = array_sum(array_column($remaining, 'size_bytes'));
        $totalGb = $totalBytes / (1024 ** 3);
        $maxSizeBytes = $maxSizeGb * (1024 ** 3);

        if ($totalBytes > $maxSizeBytes) {
            $io->text(sprintf('  Total size %.2f GB exceeds limit %d GB — removing oldest indices.', $totalGb, $maxSizeGb));

            usort($remaining, static fn (array $a, array $b): int => strcmp($a['date'], $b['date']));

            foreach ($remaining as $entry) {
                if ($totalBytes <= $maxSizeBytes) {
                    break;
                }

                $io->text(sprintf('  [size] %s (%.2f MB)', $entry['index'], $entry['size_bytes'] / (1024 ** 2)));

                if (!$dryRun) {
                    $this->indexManager->deleteIndex($entry['index']);
                }

                $totalBytes -= $entry['size_bytes'];
                ++$deleted;
            }
        }

        $action = $dryRun ? 'Would delete' : 'Deleted';
        $io->success(sprintf('%s %d index(es).', $action, $deleted));
    }

    private function cleanupAuditRecords(SymfonyStyle $io, int $maxAge, bool $dryRun): void
    {
        $io->section('Audit records (a2a_message_audit)');

        $cutoff = (new \DateTimeImmutable())->modify(sprintf('-%d days', $maxAge))->format('Y-m-d H:i:s');

        $count = (int) $this->connection->fetchOne(
            'SELECT COUNT(*) FROM a2a_message_audit WHERE created_at < :cutoff',
            ['cutoff' => $cutoff],
        );

        if (0 === $count) {
            $io->success('No old audit records to clean up.');

            return;
        }

        $io->text(sprintf('Found %d audit record(s) older than %d days (before %s).', $count, $maxAge, $cutoff));

        if (!$dryRun) {
            $this->connection->executeStatement(
                'DELETE FROM a2a_message_audit WHERE created_at < :cutoff',
                ['cutoff' => $cutoff],
            );
        }

        $action = $dryRun ? 'Would delete' : 'Deleted';
        $io->success(sprintf('%s %d audit record(s).', $action, $count));
    }
}
