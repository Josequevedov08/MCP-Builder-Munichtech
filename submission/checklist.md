# Submission checklist

Deadline: submit before 9:30. Hard limit about 11:00.

## Code and repository

- [ ] All tests pass locally: `python -m pytest tests -q`
- [ ] Commit and push to `main` (Jesus is a co-author of the commit, and a collaborator in the repository)
- [ ] GitHub Actions: "Tests" and the Pages deploy are green
- [ ] `.env` is not in the repository (`git ls-files | grep .env` shows only `.env.example`)
- [ ] The repository is public

## Live service

- [ ] https://mcpbuilder-api.quevedojose.com/api/health returns `"status": "ok"` with the model name and `"voice_enabled": true`
- [ ] https://mcpbuilder.quevedojose.com loads and the status card shows both services online
- [ ] Do one full build on the live site: fill the form, demo checkout, hear the report, download and unzip the .zip, run `npm install` and `npm run build`
- [ ] Try the site in German and Spanish
- [ ] Receipt email: `email_enabled` is `true` in `/api/health`, and a test purchase with a second address (not the account owner) delivers the email with the .zip attached
- [ ] If the Resend domain is not verified, remember the test sender only delivers to the account owner's address
- [ ] Render: the service is awake right before submitting (open the health URL)

## Devpost

- [ ] Project name, elevator pitch and text from `devpost-text.md`
- [ ] Image `site/brand/devpost-project-image-1800x1200.png`
- [ ] Video uploaded (YouTube or Vimeo, public or unlisted), under 3 minutes
- [ ] Links: website, repository, health URL
- [ ] Built with tags filled in
- [ ] Team members added: Jose Quevedo and Jesus Nolaya (invite by email if needed)
- [ ] Submit the project (not only save the draft) and check the confirmation

## After the submission

- [ ] Rotate the Featherless and ElevenLabs keys that were used during development, and update them in Render
- [ ] Keep the Render service running until the judging ends
