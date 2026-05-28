# Website deployment plan

## Domains

- `largestack.ai` -> main website
- `www.largestack.ai` -> main website
- `docs.largestack.ai` -> documentation
- `app.largestack.ai` -> SaaS beta later
- `api.largestack.ai` -> API later
- `largestack.dev` -> redirect to docs or GitHub
- `largestack.tech` -> redirect to largestack.ai

## Recommended DNS

Use Cloudflare DNS.

Example DNS mapping:

| Type | Name | Target |
|---|---|---|
| CNAME | www | website hosting target |
| CNAME | docs | docs hosting target |
| CNAME | app | SaaS hosting target |
| CNAME | api | API hosting target |

## Email

Use Cloudflare Email Routing first:

- hello@largestack.ai
- support@largestack.ai
- founder@largestack.ai

Forward them to the founder inbox.

Later use Google Workspace or Zoho Mail for full sending mailbox.
