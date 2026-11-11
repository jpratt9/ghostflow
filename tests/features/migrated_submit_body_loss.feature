@e2e @e2e_image
Feature: A failure after the submit click never bills a second generation
  Chrome can refuse to return a reply body (#1009). On the image submit reply that
  used to reach the client's retry loop, which ran the whole submit again: one
  `--count 1` run left two images in the project (#1010, spike 2026-10-21).

  Flow still makes the image, so it is read off the project grid instead (#1075).

  Scenario: An image submit whose reply body is lost is recovered, not re-submitted
    Given an image submit whose reply body Chrome cannot return
    When gflow generates the image on the migrated host
    Then exactly one image submit reached Flow
    And gflow returns the one image the submit made, downloadable

  Scenario: An image-to-image submit whose reply body is lost returns the output, not its reference
    Given an image submit whose reply body Chrome cannot return
    When gflow generates an image from a local reference on the migrated host
    Then exactly one image submit reached Flow
    And gflow returns the one image the submit made, not the uploaded reference
