@e2e @e2e_image
Feature: flow.google.com's own refusal reaches the user as that refusal
  A submit Google's bot check refuses comes back as HTTP 200 carrying a
  PUBLIC_ERROR_UNUSUAL_ACTIVITY error envelope. The wire shape is pinned offline in
  migrated_refusal_envelope.feature; this proves Flow still sends it.

  Scenario: A submit whose reCAPTCHA token is corrupted in flight is refused by name
    Given an image submit whose reCAPTCHA token is corrupted on its way to Flow
    When gflow generates the image on the migrated host
    Then gflow raises a WAF rejection naming PUBLIC_ERROR_UNUSUAL_ACTIVITY
    And only one corrupted submit reached Flow
