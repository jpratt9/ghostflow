@e2e @e2e_image
Feature: An MCP wait=false generation runs in the background of the server
  Before #1097, wait=false saved the job and returned a task id that nothing ever ran,
  so tasks/get said "working" forever. The job now runs inside the gflow mcp run
  process that accepted it, and tasks/get carries what wait=true would have returned
  (SEP-2663, #1102).

  Scenario: a queued image job completes and its result is readable
    Given a gflow mcp run server over stdio on the e2e profile
    When the agent calls gflow_generate_image with wait false
    Then the reply is pending with a task id
    And tasks/get eventually reports the task completed
    And the completed task carries an image file that exists on disk

  Scenario: closing the client mid-job leaves a truthful row and no browser
    Given a gflow mcp run server over stdio on the e2e profile
    When the agent calls gflow_generate_image with wait false
    And the client closes the server once the job is running
    Then the server exits within 60 seconds
    And the job's row is no longer processing
    And no browser on the e2e profile is left running
