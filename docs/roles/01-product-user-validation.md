# 01 · Product manager / user validation

**Owned outcome:** a specific, validated analyst-review task and clear acceptance criteria.

## Product definition

Target users are small-to-medium analytics teams that use different AI coding assistants against shared business definitions. A syntactically valid query can still calculate a different metric from the team's intended one. TeamGuard gives the team a single review standard and a traceable place to inspect proposed corrections before use.

The initial story about roughly twenty analysts using different coding agents is a hypothesis from the group discussion, not an observed customer study. The submitted plan lists CUHK(SZ) as sponsor; this does not establish that an external practitioner has validated the problem. No interviews or user-feedback results are claimed in this release.

## User journeys and acceptance criteria

| User task | Successful behavior | Evidence in the implementation |
| --- | --- | --- |
| Owner sets a review standard | Save a schema and rules as a version; inspect old versions | Project & rules, `Rulebook`, `Store.save_rulebook` |
| Analyst reviews generated SQL | Paste/upload one query and receive a distinguishable passed/needs-review/incomplete outcome | Submit SQL, `review_sql` |
| Reviewer understands a finding | Inspect SQL evidence, applicable rule and proposed correction | Review report tabs |
| Reviewer records a judgment | Accept/reject with an alias and note, without executing SQL | `Decision`, history |
| Team checks consistency | Search earlier reports and retain the exact old rule version | Snapshot stored in every report |

The MVP excludes shared code editing, collecting coding-assistant conversations, employee monitoring, production database writes and automatic code merging. Token data is per-request operational evidence, not an employee surveillance feature.

## Validation protocol to run with at least three proxy users

Recruit an analyst, someone who reviews analytics code, and a credible proxy user unfamiliar with the implementation. Explain that this is a synthetic local demonstration and obtain permission before keeping their comments. Use aliases in notes; do not collect confidential SQL.

Give each participant the same tasks without steering their clicks:

1. Review the bad recognized-revenue example and explain what is wrong in their own words.
2. Find the quoted rule and compare the proposed SQL with the original.
3. Record accept or reject with a reason. Explain what that decision does and does not do.
4. Find the original report in History after opening another page.
5. Open a correct query and an incomplete report; explain the difference between passed and incomplete.

Record task completion, elapsed time, where help was required, whether the explanation of the finding was correct, and the user's own objections. Separate observed behavior from interview comments. Ask: “What would you need to trust this finding?”, “Which definition differs from your team's practice?” and “What would make you reject the suggested SQL?” Avoid asking leading questions such as whether the app is useful.

## What to change based on feedback

| Observation | Candidate response | Required recheck |
| --- | --- | --- |
| Users interpret acceptance as execution | Clarify decision text and placement | Repeat task 3 without hints |
| A rule is unclear or not applicable | Rewrite the rule with the data lead; create a new version | Keep old reports intact and rerun affected cases |
| Users cannot locate original evidence | Adjust the report hierarchy | Repeat tasks 2 and 4 |
| Review latency interrupts the task | Measure live waits separately from structural-only cases | Compare completion and waiting behavior |

These are response options, not claims that the problems were observed externally.

## Current status and handoff

The main journeys are implemented and exercised through automated/interface checks and a developer-operated browser walkthrough. Independent user validation and willingness-to-adopt evidence remain pending. The evaluation lead must distinguish developer test results from user-study results.

Hand off agreed metric definitions to the workflow and data leads; pass observed usability problems to the application owner; give the demo owner a short, factual problem statement. Before the final report, replace hypotheses with documented feedback where available and state clearly where evidence is still missing. Actual member contributions must be confirmed separately from these assigned responsibilities.
