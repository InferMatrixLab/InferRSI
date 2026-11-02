# agent-CI-Infra bot integration

This runbook connects InferRSI to the existing
[bot service](https://github.com/agent-CI-Infra/bot), following its
[onboarding guide](https://github.com/agent-CI-Infra/bot/blob/main/docs/onboarding-guide.md)
and [repository rules contract](https://github.com/agent-CI-Infra/bot/blob/main/docs/rules.md).
Repository files alone do not install the App, start a project or publish a board.
Track activation and verification in the governing onboarding Issue.

## Repository configuration

- [Bot guide](../../.bot/guide.md): supplements the repository's entry,
  contribution, collaboration and security contracts.
- Python setup uses the project image's existing Python, pip and venv. Each task
  creates a checkout-local virtual environment as described in the guide. No
  `.bot/computer.yaml` override, GPU/NPU, secrets or extra apt packages are needed.
- [Board inputs](agent-ci-board.json): the optional `config_json` input for
  the dashboard's `Create board` workflow; it does not change source CI.

Bot text rules replace their lower-priority counterpart in full. The guide
retains the upstream requirements to inspect code/tests, ground conclusions,
leave GitHub publication to the control plane, and avoid merges or credential
disclosure. No task-specific prompt or label rule is replaced. Machine settings
remain with the deployment administrator. Do not configure a shared editable
Python installation: concurrent tasks must import their own checkouts.

Rules become effective after merging into the default branch. PR review reads
rules from the default branch, not the proposed PR. Issue tasks read their
configured base branch, which must contain the rules too. An initial review of
this integration therefore still uses the previously effective rules.

## Activate the service

1. The repository owner opens the
   [GitHub App installation page](https://github.com/apps/agent-ci-infra-bot/installations/new),
   selects the organization and **Only select repositories → InferRSI**, reviews
   the requested permissions, then confirms installation. App-level permissions
   and installation approval are separate. The service requests broad write
   permissions, including repository administration and workflows; the owner
   must review the actual GitHub permission screen.
2. Log into the
   [control console](https://agent-ci-infra-bot-admin.llmbots.co/), completing
   Cloudflare Access first if prompted. Do not put passwords, email verification
   codes, API keys or session cookies in repository files or Issues.
3. An authorized administrator synchronizes installations, locates the canonical
   `InferMatrixLab/InferRSI` project, selects an already approved configured model,
   and starts **review only**, with development off. If the console cannot
   express the required knowledge-authorship settings, leave protected changes
   to qualified contributors; do not bypass the policy.
4. Verify the project is enabled and working. Refresh its rule overview after
   the configuration PR merges. On a subsequent in-scope Issue or PR, verify a
   successful webhook delivery, completed review task and published review.
   Record links and any limitations in the onboarding Issue. Old events are not
   replayed merely by starting the project.

Automatic development and automatic merging require separately accepted scope.
If development is later enabled, the upstream service additionally requires a
human-applied development label (default `bot-develop`) and an unassigned open
Issue. These service conditions do not replace InferRSI's Issue authorization,
independent review, DCO or knowledge admission requirements.

## Board and public dashboard

InferRSI uses Python and already has draft, ready, merge and nightly workflows.
Skip the console's **gate PR** action: its current implementation requires
`package.json` and adds Node CI/nightly templates. Do not add a dummy Node project
or rename existing workflows to satisfy that detector. A console gate status of
none/configured is not a verdict about InferRSI's own checks.

An authorized dashboard maintainer can run
[`Create board`](https://github.com/agent-CI-Infra/dashboard/actions/workflows/board-create.yml)
with `source_repository=InferMatrixLab/InferRSI` and the contents of
[`agent-ci-board.json`](agent-ci-board.json) as `config_json`. The current console
board action does not pass custom workflow mappings, so use the workflow directly
for these inputs, or have the maintainer update an already created board's
`board-config.json` in place instead of creating a duplicate board.

The mapping recognizes current workflow names without changing them. The board
classifies runs by both workflow and event: ready PR runs appear under PR, merge
pushes under main, and nightly under daily. It also includes the knowledge
declaration policy alongside CI and the existing release bot under release.
Draft non-main pushes are not shown in that calendar by the current collector.
Other specialized workflows are outside this mapping. The board's display
categories are not new InferRSI CI lanes.
No ci-gates report artifacts or L1–L4 measurements are generated by this setup.

The dashboard workflow creates `board/infermatrixlab/inferrsi` and starts initial
collection. Verify both `Collect board data` and `Deploy to GitHub Pages`, then
inspect the published snapshot for the correct repository, workflows and real
run conclusions. The intended address is
[the InferRSI board](https://agent-ci-infra.github.io/dashboard/boards/infermatrixlab/inferrsi/);
this link is not proof that publication has completed.

Only after the board exists, run the console's separate **Dashboard registration**
action and review its PR in `agent-CI-Infra/dashboard`. The dashboard maintainers
review and merge it; verify a later collection includes InferRSI. The source is
public, so it needs no `PRIVATE_SOURCE_TOKEN`. Do not publish extra contributor
identities or copy private infrastructure information during registration.

Deployment is complete only after App installation, project activation, an
observed bot review and the requested board/dashboard publication are verified.
A merged configuration PR is only the repository portion of that work.
