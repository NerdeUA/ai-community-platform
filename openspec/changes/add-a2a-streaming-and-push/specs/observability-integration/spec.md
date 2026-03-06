## ADDED Requirements

### Requirement: Async A2A Trace Correlation
The platform observability contract SHALL preserve `trace_id`, `request_id`, and `task_id` across polling, SSE streaming, and push notification flows.

#### Scenario: SSE update carries correlation fields
- **WHEN** the gateway emits an SSE task update event
- **THEN** the event payload includes `trace_id`, `request_id`, and `task_id`

#### Scenario: Push callback carries correlation fields
- **WHEN** the gateway delivers a push callback
- **THEN** the callback payload includes `trace_id`, `request_id`, and `task_id`

### Requirement: Async Delivery Telemetry
The platform SHALL emit structured telemetry for stream lifecycle and push delivery attempts.

#### Scenario: Stream lifecycle is observable
- **WHEN** a streaming session starts and ends
- **THEN** logs/spans include status, duration, and terminal reason

#### Scenario: Push delivery attempt is observable
- **WHEN** the gateway attempts webhook delivery
- **THEN** logs/spans include attempt number, response status, and final delivery status
