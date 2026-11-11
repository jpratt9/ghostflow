@e2e @e2e_auth
Feature: gflow credits reads the balance flow.google.com shows (#795)
  labs.google's session URL answers HTTP 410 to every account since 2026-10-22, so the
  balance can no longer come from a labs token. flow.google.com loads it itself, on the
  app's own nzlxg reply, and that is the number its account menu shows.

  Scenario: credits user reads a live balance from flow.google.com
    Given a live profile that reaches the Flow app
    When I run "gflow credits user --json" for that profile
    Then the command exits 0
    And the JSON reports a non-negative integer balance for that profile
    And the balance equals the number Flow's account menu shows
