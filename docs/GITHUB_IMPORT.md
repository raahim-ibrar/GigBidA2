# GitHub portfolio import

Open Portfolio and use “Import a public GitHub project.” Supply the canonical
repository URL, a project title, optional skills and a branch/tag/commit (default HEAD).
The authenticated API requires the normal session cookie and CSRF token. A read-only
server-side `GITHUB_TOKEN` must have access to the selected public repository.

The importer connects to GitHub's official `https://api.githubcopilot.com/mcp/`
server with read-only mode and an allowlist of three tools: search_repositories,
get_commit and get_file_contents. It confirms public visibility, resolves the ref
to a 40-character commit SHA, then retrieves `README.md` at that immutable commit.
Only one nonempty text resource, at most 1 MiB, is accepted. The MCP status message
is never substituted for file content. Other hosts, arbitrary paths, private repos,
binary files and recursive dependency imports are unsupported.

The existing tenant-scoped ingestion pipeline saves and queues the README. Its
commit and source URL are retained in document metadata and shown in the UI.
Reimporting unchanged content is idempotent; updated content follows normal source
revision and vector replacement rules. Queue outages preserve the saved source for
worker reconciliation. A repository alone does not prove authorship or paid-client
results, and embedded README instructions remain untrusted text.

`evals/results/public-integrations.json` records a successful real import of this
assignment repository, its resolved commit and ready indexing status. Contract and
integration tests separately exercise fixed-host access, immutable refs, CSRF,
authentication, duplicate imports and account isolation.
