@e2e @e2e_video
Feature: r2v clips with saved characters, one or two per clip, on flow.google.com (#723)
  A cast matrix that separates the character from the code. Two voiceless characters
  live in one project: a stylized one (A) and a photoreal person (B). Each row names a
  cast by those letters. Needs GFLOW_CLI_E2E_PROJECT and GFLOW_CLI_E2E_CAST, for example
  "A=Bolt:<entity-id>,B=Nora:<entity-id>". Every row spends Veo credits
  (GFLOW_CLI_E2E_RUN_VIDEO=1); run the file several times to measure repeatability.

  Scenario Outline: The CLI generates an r2v clip of <cast> with a local reference
    Given a project on flow.google.com with the matrix cast
    When the CLI generates an r2v clip of cast "<cast>" with a local reference image
    Then the command succeeds and writes the clip
    And the characters attached were exactly cast "<cast>"

    Examples:
      | cast |
      | A    |
      | B    |
      | A+B  |

  Scenario Outline: The MCP video tool generates an r2v clip of <cast>
    Given a project on flow.google.com with the matrix cast
    When the MCP video tool generates an r2v clip of cast "<cast>" with reference "<ref>"
    Then the task completes with the clip on disk, attaching exactly cast "<cast>"

    Examples:
      | cast | ref  |
      | A    | blue |
      | B    | blue |
      | A+B  | blue |
      | A    | none |
