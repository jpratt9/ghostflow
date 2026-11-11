@e2e @e2e_image
Feature: A generated image whose download fails is still recorded
  Flow generates the image and spends the day's quota before gflow writes a byte. When
  the local write then fails, the media id was lost with the traceback, and the catalog
  kept only a FAILED row with no project and no asset (#1035). The generation must stay
  reachable: its media id in the catalog, one FAILED operation in its project.

  Scenario: image t2i into a directory it cannot write keeps the media id
    Given an output directory gflow cannot write to
    When image t2i runs with --out pointed at that directory
    Then the run fails and stderr names the media id and the project, with no signed URL
    And the failure exits 11 as a configuration error, not as an unexpected error
    And the catalog keeps the media id with no local copy, under one FAILED operation

  Scenario: the MCP image tool writing to a path it cannot write reports the media id
    Given an output directory gflow cannot write to
    When the MCP image tool generates into that directory
    Then the failed task carries the media id and the project id
    And the catalog keeps the media id with no local copy, under one FAILED operation
