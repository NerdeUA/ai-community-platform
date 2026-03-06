<?php

declare(strict_types=1);

namespace App\Logging\DTO;

/**
 * Status of a trace event within a processing step.
 */
enum TraceStatus: string
{
    /** Processing step has started */
    case Started = 'started';

    /** Processing step completed successfully */
    case Completed = 'completed';

    /** Processing step failed */
    case Failed = 'failed';
}
