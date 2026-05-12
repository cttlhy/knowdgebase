## ADDED Requirements

### Requirement: Retry only on explicitly recoverable LLM call failures
The system MUST retry LLM calls only for explicitly recoverable failures:
- timeout errors (request timeout / read timeout)
- transient network I/O errors (connection reset, temporary DNS/connect failure)
- HTTP `429`
- HTTP `5xx`

The system MUST NOT retry:
- HTTP `4xx` errors other than `429`
- cancellation/interrupt errors raised by user or runtime
- response format errors defined in this spec

#### Scenario: Retry on timeout
- **WHEN** a single LLM call fails with a timeout error
- **THEN** the system retries the same call until success or retry budget is exhausted

#### Scenario: Retry on HTTP 429
- **WHEN** a single LLM call returns HTTP status `429`
- **THEN** the system treats it as retryable and schedules the next attempt with backoff delay

#### Scenario: Do not retry on HTTP 400
- **WHEN** a single LLM call returns HTTP status `400`
- **THEN** the system marks this call as non-retryable and fails this item immediately

### Requirement: Retry budget and delay parameters are fixed and testable
The system MUST apply `max_retries=3`, where the count includes the first attempt.  
Therefore, the maximum total attempts per item is `3`.  
The system MUST use exponential backoff from `base_delay=1s` with delay sequence `1s -> 2s -> 4s` before jitter.  
The system MUST cap delay by `max_delay=20s`.  
The system MUST apply jitter multiplier in range `1.0~1.5`, and the jitter MUST NOT reduce the base backoff delay.

#### Scenario: Retry budget exhausted
- **WHEN** a call fails with retryable errors for three total attempts
- **THEN** the system stops retrying and marks the item as failed

#### Scenario: Jitter only increases delay
- **WHEN** the system computes delay for a retryable failure
- **THEN** the final delay is greater than or equal to the non-jitter exponential delay

### Requirement: Non-retryable response format errors fail fast
The system MUST treat response format errors as non-retryable, including:
- malformed JSON (cannot be parsed)
- parsed JSON missing required analyzer keys expected by pipeline parsing logic

#### Scenario: Malformed JSON response
- **WHEN** the analyzer receives model output that cannot be parsed into JSON
- **THEN** the system does not retry this item due to format error

#### Scenario: Missing required keys
- **WHEN** parsed JSON is missing required keys used by analyzer parsing logic
- **THEN** the system does not retry this item due to format error

### Requirement: Item-level failure isolation in batch analysis
The system MUST continue processing remaining items when one item reaches terminal failure after retry handling.  
The system MUST NOT abort the entire pipeline due to one failed item in the analyze stage.

#### Scenario: One failed item does not stop batch
- **WHEN** item A fails terminally and item B is still pending in the same run
- **THEN** item B is still analyzed in the current batch run

### Requirement: Retry and terminal-failure logs must include context
For each retry event, the system MUST log:
- item `title`
- item `url`
- attempt progress (current/total)
- error type (and HTTP status code when available)
- planned delay

For terminal failure, the system MUST log that the item is abandoned and processing continues.
If `title` or `url` is missing, the system MUST log `"<missing>"` as fallback value.

#### Scenario: Retry log fields are complete
- **WHEN** a retryable failure occurs
- **THEN** the log entry contains item title, item URL, attempt progress, error type, and delay duration

#### Scenario: Terminal abandon log is explicit
- **WHEN** an item reaches max retry attempts without success
- **THEN** the log explicitly states the item is abandoned and the pipeline continues with next item
