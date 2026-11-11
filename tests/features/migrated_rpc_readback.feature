@e2e @e2e_auth
Feature: Persisted writes survive an unavailable Chrome response body
  Scenario: Create, its rename and an upload recover by independent project readback
    Given a real signed-in Flow browser
    When a project create, the rename inside it and an upload commit but their response bodies cannot be read
    Then each write is recovered without resubmission and a reload of the original page shows it
