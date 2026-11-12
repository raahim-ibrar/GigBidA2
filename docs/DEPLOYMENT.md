# No out-of-pocket deployment: student-credit VM + Vercel

This is a prepared deployment configuration, not a claim that a live site exists.
The frontend runs on Vercel Hobby. A single Azure for Students VM runs the API,
worker, Postgres, Redis, Qdrant and student simulator with durable Docker volumes.
Hosted Groq open-weight inference avoids a GPU requirement. Fresh server data uses
synthetic scenarios; do not transfer the local private CV/database as a deployment shortcut.

## Eligibility and cost boundary

Use the **Azure for Students** offer, subject to university/student verification:
https://azure.microsoft.com/en-us/free/students/. Microsoft advertises USD 100
credit, no credit card, and a 12-month credit term. This is limited credit, not
permanent unlimited hosting. Keep the student subscription's spending limit on;
do not upgrade to Pay-As-You-Go or attach paid Marketplace services. Credit expiry
or exhaustion disables services unless the account is explicitly upgraded.

Sources checked November 12, 2026:

- https://azureforeducation.microsoft.com/en-us/Student
- https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/azurestudents-subscription-disabled
- https://vercel.com/docs/monorepos
- https://vercel.com/docs/daemons

The VM, disk and network consume student credit. Inspect the portal's actual
estimate and remaining credit before provisioning. No resources have been
provisioned by these files. Do not choose a GPU, paid image, managed database or
paid Vercel plan. Groq free-tier limits remain separate and can pause generation.

## Backend VM

1. Activate the student subscription and verify its credit/spending-limit state.
2. Use a standard Ubuntu LTS x86-64 VM, initially 2 vCPU and 4 GiB RAM if available
   within the account's credit/quota. Avoid a paid OS image. Actual regional price
   and availability must be checked in the portal; this document makes no price promise.
3. Use SSH keys. Allow SSH from the administrator's current IP; allow public TCP
   80/443 for HTTPS. Do not expose 5432, 6379, 6333, 8000 or 8080.
4. Give the public IP a provider DNS label. Record its exact hostname, for example
   `gigbid-api.REGION.cloudapp.azure.com`, and verify DNS resolves to the VM.
5. Install Docker Engine with the Compose plugin, clone the repository at the
   intended deployment commit, and prepare `.env.cloud` in the repository root.
   Use `infra/cloud.env.example` as the template. The real file is Git-ignored.
6. Set `API_DOMAIN` to the actual VM hostname and `WEB_ORIGIN` to the exact Vercel
   production origin. Generate separate random 64-character hexadecimal secrets
   for Postgres and simulator access. Add the existing Groq key privately. Do not
   paste keys in chat or put them into `NEXT_PUBLIC_*` variables.
7. Restrict the real env file with `chmod 600 .env.cloud`, then run:

```sh
docker compose --env-file .env.cloud -f infra/compose.cloud.yml config --quiet
docker compose --env-file .env.cloud -f infra/compose.cloud.yml up -d --build
docker compose --env-file .env.cloud -f infra/compose.cloud.yml ps
```

`config --quiet` validates without printing expanded credentials. Caddy obtains
and renews the backend HTTPS certificate when public DNS/ports are correct.
The migration service must complete successfully before the API/worker starts.
Only the proxy publishes ports. Redis uses AOF, and simulator SQLite, Postgres,
Qdrant and model caches have named volumes. Do not use `down --volumes` on the VM.
Backups must include the database and simulator state; a volume is not a backup.

## Vercel frontend

Import `raahim-ibrar/GigBidA2`, choose **Root Directory `apps/web`** and the Next.js
framework preset. Use the personal Hobby plan. `apps/web/vercel.json` supplies
`npm ci` and `npm run build`; leave the output directory on its framework default.

Set this server-side variable for the production deployment:

```text
API_INTERNAL_URL=https://ACTUAL_BACKEND_HOSTNAME
```

It must be the HTTPS origin, without `/api`, credentials or a trailing path.
Leave `NEXT_PUBLIC_API_URL` unset so browser requests remain same-origin under
`/api/*`; Next.js proxies them to the backend. Do not place model/database keys in
the frontend project. Vercel builds explicitly fail when pointed at localhost or
when the backend origin is missing. A placeholder used for a build check is not
a deployed backend. If using a preview URL interactively, the backend must allow
that exact origin; the production origin remains the stable reviewer URL.

The standalone output/postbuild path is retained for local Docker deployment.
On Vercel, native Next.js output is used instead. No Docker worker or local model
is embedded into the frontend deployment.

## Live checks before calling it deployed

- Backend HTTPS `/health/ready` returns success, with a valid certificate.
- The Vercel `/api/status` route reaches that same backend.
- Account signup/login produces Secure cookies; CSRF-protected writes work.
- A synthetic portfolio uploads and indexes through the actual worker/Qdrant.
- A synthetic job reaches review. Approval creates exactly one simulator receipt;
  reload/retry does not debit twice. No real marketplace client is contacted.
- Restart the backend containers and confirm accounts, portfolio, checkpoints and
  simulator receipts survive. Close the laptop and verify the cloud URL still works.
- Supply reviewer credentials privately. Record the deployed commit and real URLs.

The public Portfolio MCP endpoint and any remaining integration/tracing requirements
must be verified separately; a frontend URL alone does not satisfy those deliverables.

## Credit expiry and cleanup

The account owner must monitor student credit and delete the VM, disks, public IP
and related resources after grading when no longer needed. Do not remove the
student spending limit to extend uptime. This setup is no out-of-pocket only while
the eligible credit-backed subscription remains capped and no paid upgrade occurs.
