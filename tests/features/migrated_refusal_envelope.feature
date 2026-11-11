Feature: A refusal flow.google.com states on the wire is reported as that refusal
  flow.google.com answers a refused submit with HTTP 200 and a batchexecute error
  envelope: a null payload and a gRPC status carrying Google's ErrorInfo reason.
  Measured 2026-09-27 (spike 2026-09-27-migrated-refusal-is-on-the-wire). gflow used
  to drop that frame and report a timeout or a wire-format fault instead.

  Scenario: An unusual-activity refusal of an image submit is a WAF rejection
    Given the migrated host refuses an image submit for unusual activity
    When the image submit is observed
    Then gflow raises a WAF rejection naming PUBLIC_ERROR_UNUSUAL_ACTIVITY

  Scenario: An unusual-activity refusal of a video submit fails fast as a WAF rejection
    Given the migrated host refuses a video submit for unusual activity
    When the video submit is observed
    Then gflow raises a WAF rejection naming PUBLIC_ERROR_UNUSUAL_ACTIVITY
    And it does not wait out the submit budget

  Scenario: A content-safety reason on the envelope is a content-policy refusal
    Given the migrated host refuses an image submit with PUBLIC_ERROR_UNSAFE_GENERATION
    When the image submit is observed
    Then gflow raises a content-policy refusal naming PUBLIC_ERROR_UNSAFE_GENERATION

  Scenario: An error envelope with no known reason is not reported as a refusal
    Given the migrated host answers a video submit with a bare status-5 envelope
    When the video submit is observed
    Then the run is not reported as a refusal
