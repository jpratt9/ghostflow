@e2e @e2e_image
Feature: An @Character mention binds the character on flow.google.com images (#723)
  On an account Flow serves from flow.google.com the character catalog is read through
  a labs route that answers 401, so the mention is attached by name through the
  composer's `@` picker. The picker lists characters and media in one list with no
  locale-invariant marker of kind, and an image captioned with the character's name can
  outrank the character, so the option TITLED exactly the name is committed — never a
  trial commit, because a chip deleted from the prompt still rides the submit — and the
  submit must carry exactly the requested references. Needs a project holding a character with a reference image:
  GFLOW_CLI_E2E_PROJECT and GFLOW_CLI_E2E_CHARACTER (a one-word name).

  Scenario: The CLI binds the character, not a media asset sharing its name
    Given a project on flow.google.com that holds the named character
    When the CLI generates "@<character> reading a potions book by the fireplace"
    Then the command succeeds and writes the image
    And the submit carried exactly the character and no other reference

  Scenario: The MCP image tool binds the same character through the queue
    Given a project on flow.google.com that holds the named character
    When the MCP image tool generates "@<character> reading a potions book by the fireplace"
    Then the task completes with the image on disk

  Scenario: The CLI binds the character next to an uploaded reference image
    Given a project on flow.google.com that holds the named character
    When the CLI generates "@<character> in the style of the reference image" with a local reference image
    Then the command succeeds and writes the image
    And the submit carried exactly the uploaded image and the character

  Scenario: A character given only by entity id is refused before submit
    Given a project on flow.google.com that holds the named character
    When the CLI generates "a quiet library" with an entity id and no name
    Then the command exits 36 naming the id-only character, with no image written
