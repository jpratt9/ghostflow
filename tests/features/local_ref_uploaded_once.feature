@e2e @e2e_image
Feature: A local reference file is uploaded into a project once
  A loop that runs image i2i with the same --ref file uploaded it again on every call on
  flow.google.com, so the project's library filled with copies of one image (#772). The
  first run uploads and records it; a later run in the same project, with the same file,
  mentions the recorded image in place.

  Scenario: a second image i2i with the same --ref file in the same project does not upload it
    Given a local reference image already used once by image i2i in a project
    When image i2i runs again with the same --ref file in that project
    Then the run succeeds and saves one image
    And the recorded upload was mentioned in place, with no second upload

  Scenario: the MCP image tool reuses a local reference the CLI uploaded to the project
    Given a local reference image already used once by image i2i in a project
    When the MCP image tool runs with the same file as a reference in that project
    Then the MCP task completes with one image on disk
    And the recorded upload was mentioned in place, with no second upload

  Scenario: a recorded upload the project no longer holds is uploaded again and re-recorded
    Given a local reference image already used once by image i2i in a project
    And the catalog records that file under an image the project does not hold
    When image i2i runs again with the same --ref file in that project
    Then the run succeeds and saves one image
    And the file was uploaded again after the miss, and the new copy recorded
