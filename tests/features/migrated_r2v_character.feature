@e2e @e2e_video
Feature: An r2v clip carries a named character on flow.google.com (#723)
  On an account Flow serves from flow.google.com, a character is attached to an r2v
  clip by NAME through the composer's `@` picker, after the uploaded reference images.
  The chips are counted before the billed click, and the MZZa6b submit body must carry
  every uploaded media id AND the committed entity id, or the run is refused before Flow
  acts. Needs a project holding a character: GFLOW_CLI_E2E_PROJECT,
  GFLOW_CLI_E2E_CHARACTER (a one-word name) and GFLOW_CLI_E2E_CHARACTER_ID (its entity
  id). The two generating scenarios spend Veo credits (GFLOW_CLI_E2E_RUN_VIDEO=1).

  Scenario: The CLI generates an r2v clip with the character and a local reference
    Given a project on flow.google.com that holds the named character
    When the CLI generates an r2v clip of the character with a local reference image
    Then the command succeeds and writes the clip
    And the character attached was the requested entity

  Scenario: The MCP video tool generates the same clip through the queue
    Given a project on flow.google.com that holds the named character
    When the MCP video tool generates an r2v clip of the character with a local reference image
    Then the task completes with the clip on disk

  Scenario: A character given only by entity id is refused before submit
    Given a project on flow.google.com that holds the named character
    When the CLI generates an r2v clip with an entity id and no name
    Then the command exits 36 naming the id-only character, with no clip written
