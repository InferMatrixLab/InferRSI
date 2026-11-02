# Self-hosted agent-CI-Infra bot

Deploy an independently administered instance of
[agent-CI-Infra/bot](https://github.com/agent-CI-Infra/bot) for InferRSI. The instance
owns its administrator accounts, database, encryption keys, GitHub App and model
configuration. Follow the upstream [administrator guide](https://github.com/agent-CI-Infra/bot/blob/main/docs/admin.md)
and [deployment reference](https://github.com/agent-CI-Infra/bot/blob/main/docs/deployment.md).
Keep actual connection details and credentials outside this repository.

## Deploy the backend

Use an isolated deployment directory on the selected Linux host with Docker and
Docker Compose installed. Set a unique Compose project name so the instance owns
its networks and volumes independently of other services. The bot does not need
a GPU. Do not restart Docker or replace existing inference containers.

1. Select a reviewed upstream release and fetch that release's `compose.yaml`.
   Keep the release's file beside the local override rather than editing it:

   ```sh
   mkdir -m 700 <deployment-directory>
   cd <deployment-directory>
   curl --fail --location --output compose.yaml \
     https://raw.githubusercontent.com/agent-CI-Infra/bot/<bot-release>/compose.yaml
   ```

2. Copy the repository's [loopback override](../../deploy/agent-ci/compose.override.yaml)
   to this directory and copy [`.env.example`](../../deploy/agent-ci/.env.example)
   as `.env`. Replace `<bot-release>` with the selected release. Use a Compose
   version supporting `!override`; it replaces the upstream public port mapping
   instead of retaining both public and loopback mappings. If using a downloaded
   Compose executable, verify its checksum against the official release.

3. Validate the merged configuration, pull images and start the instance:

   ```sh
   docker compose config --quiet
   docker compose pull
   docker compose up --detach
   docker compose ps --all
   curl --fail http://127.0.0.1:8792/healthz
   ```

   An isolated standalone Compose executable can run the same subcommands in
   place of `docker compose`. The project-computer image is pulled before the
   manager starts. The one-shot `key-init` and `project-image` containers should
   exit successfully; bot, manager, webhook and tunnel remain running. The
   tunnel stays inactive until its own credentials are configured.

4. From the operator's computer, forward a local administration port:

   ```sh
   ssh -N -L 127.0.0.1:8792:127.0.0.1:8792 <SSH_ALIAS>
   ```

   Open <http://127.0.0.1:8792/> and create the instance's first super-administrator
   in the browser. The operator chooses and enters the password directly. No
   account on the shared service is required. If the local port is occupied,
   change the first `8792` and open that local port instead. The page remains
   accessible only while this SSH tunnel is running.

Both host ports bind to loopback. This makes the administration page available
through SSH without publishing it on the host's network. A healthy backend and
the administrator-creation screen establish backend readiness only; GitHub
events cannot reach it until HTTPS webhook routing is configured.

## Finish integration when HTTPS is available

The current backend-first scope does not require a domain yet. Later:

1. Give the instance a dedicated HTTPS webhook origin. Use an operator-owned
   reverse proxy to its webhook listener, or the instance's own Cloudflare Tunnel
   configured with `http://webhook:8791`. Keep the administration listener separate.
   The loopback override suits a host reverse proxy; a containerized proxy needs
   a deliberately configured route, not its own container's loopback address.
2. In this instance's setup wizard, create an instance-owned GitHub App and
   confirm its installation for only `InferMatrixLab/InferRSI`. An installation
   of the shared service's App remains controlled by that service. It does not
   connect this independently hosted backend and need not be removed by setup.
3. Enter the model endpoint, API key and model name in this instance's console.
   Keep credentials out of `.env`, Compose files, command arguments and Issues.
   For protected knowledge changes, follow `docs/knowledge-model-policy.md` and
   qualify actual model/effort settings before allowing those contributions.
4. Synchronize installations and start InferRSI with review enabled and
   development disabled. Verify webhook acceptance, a completed review task and
   its published response on an in-scope Issue or PR. Starting the project does
   not replay events received while it was disabled.

GitHub confirmation, administrator credentials and model setup are separate
from container health. Record their actual state in the governing Issue; do not
describe an initialized backend alone as a working GitHub review integration.

## Repository rules and CI board

[`.bot/guide.md`](../../.bot/guide.md) supplements InferRSI's contribution,
collaboration, privacy and evidence contracts. It retains the upstream
publication/no-merge boundaries and creates checkout-local Python environments
to isolate concurrent tasks. The project image already contains Python, pip and
venv, so no `.bot/computer.yaml` override is needed. Repository text rules replace
their lower-priority counterpart in full and become effective after merging
into the task's rule-source branch; the proposed PR does not govern its own
initial review. See the upstream [rule contract](https://github.com/agent-CI-Infra/bot/blob/main/docs/rules.md).

Keep InferRSI's draft → ready → merge → nightly workflows. The onboarding
service's gate PR currently requires Node package scripts and should be skipped
for this Python repository. CPU tests and dashboard indicators do not establish
campaign `PASS` or L1–L4 evidence.

Dashboard deployment is optional and separate from this backend. The
[board inputs](agent-ci-board.json) describe the existing CI workflows, knowledge
declaration policy and release bot for a compatible independently managed
dashboard. Its collector omits draft non-main pushes from the calendar; other
specialized workflows are outside the mapping. These display categories do not
create new source CI lanes or measurements. Configure and review the destination
dashboard before using the console's board/registration actions: upstream
defaults target the shared dashboard. No public registration is required for
the self-hosted backend.

## Maintain the instance

Record the selected release and actual image digests in local deployment records.
Validate Compose after changing its release or override, then pull and restart
only this project. Check backend health and access again after an upgrade.

Back up the control database, encryption keys, internal authentication, manager
ledger and any dynamic project work volumes together, using the upstream
stop-and-copy procedure. Missing encryption keys prevent credential recovery;
missing internal authentication changes resource ownership. Preserve volumes
during ordinary maintenance; `down --volumes` deletes instance state. Docker
access belongs only to the manager, whose Docker socket access grants host
container-management capability. Keep its port internal.
