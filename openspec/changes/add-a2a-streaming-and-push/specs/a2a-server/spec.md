## ADDED Requirements

### Requirement: Agent Card Async Capability Declaration
A2A Servers SHALL declare async interaction support in Agent Card capabilities using explicit flags for `streaming` and `pushNotifications`.

#### Scenario: Agent declares streaming support
- **WHEN** an agent supports server-sent event streaming
- **THEN** its Agent Card includes `capabilities.streaming: true`

#### Scenario: Agent declares push support
- **WHEN** an agent supports webhook push notifications
- **THEN** its Agent Card includes `capabilities.pushNotifications: true`

### Requirement: Streaming Responses over SSE
The A2A Gateway SHALL expose a streaming message flow that returns `text/event-stream` and emits task status/artifact updates until a terminal state is reached.

#### Scenario: Streaming request accepted
- **WHEN** a client calls the streaming send-message API with valid auth and payload
- **THEN** the gateway responds with HTTP 200 and `Content-Type: text/event-stream`
- **AND** emits ordered task update events

#### Scenario: Stream closes on terminal task state
- **WHEN** the task reaches a terminal state (`completed`, `failed`, `canceled`, `rejected`, `input_required`)
- **THEN** the gateway emits the final event and closes the stream

### Requirement: Polling-Compatible Task Retrieval
The A2A Gateway SHALL provide task retrieval for clients that cannot hold persistent connections.

#### Scenario: Client retrieves latest task state
- **WHEN** a client requests task details by `task_id`
- **THEN** the gateway returns the latest persisted task state and artifacts snapshot

### Requirement: Push Notification Configuration
The A2A Gateway SHALL allow clients to register webhook push configuration per task.

#### Scenario: Client registers push webhook
- **WHEN** a client submits a valid push configuration (`url`, optional token, auth metadata)
- **THEN** the gateway stores the configuration and associates it with the task

### Requirement: Authenticated Push Delivery
Push notifications SHALL be authenticated and replay-resistant.

#### Scenario: Gateway sends signed/authenticated push callback
- **WHEN** a significant task update occurs for a task with push configuration
- **THEN** the gateway sends an authenticated HTTP POST callback to the configured webhook
- **AND** includes metadata required for replay protection and deduplication
