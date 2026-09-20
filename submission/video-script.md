# Three minute video script

Record the screen with your voice. Keep the total under 3:00. Practice once with the real site so the timings are true. Turn the sound of your computer on so the ElevenLabs report is recorded.

Before recording: open the API health URL so the server is awake, open the site in English, and have a terminal ready in an empty folder.

| Time | On screen | What you say |
| --- | --- | --- |
| 0:00 to 0:15 | Landing page hero | "Connecting your data to an AI takes days of work with MCP. And for a blind developer, build tools are even harder, because progress is shown on a screen. MCP Builder fixes both." |
| 0:15 to 0:35 | Live service status card | "The page checks the live service. The open-weight model on Featherless.ai and the ElevenLabs voice are both online." |
| 0:35 to 1:10 | Quote builder: choose Database, name `clinic-patients`, tables `patients, appointments`, instruction "Read only. Never show phone numbers or diagnosis." | "I choose a database, name my server and list the tables. Then I write my rules in plain words. I do not write any code." |
| 1:10 to 1:25 | Checkout: click "Fill in test card", pay | "The payment is a demo, nothing is charged. That is stated on the page." |
| 1:25 to 1:55 | Result page: the spoken report plays, then the rules list | "Now the build report is read aloud, in the language I chose. The same text is on the page for screen readers. Below are the rules the AI derived from my sentence: read only, phone and diagnosis blocked, row limit. I can verify what it understood." |
| 1:55 to 2:15 | File preview, click Download server.zip, then show the receipt email with the .zip attached | "The AI only writes this small policy. The server code comes from templates that we compile and test, so it always builds and the security checks are always there. The same .zip also arrives by email with the receipt." |
| 2:15 to 2:40 | Terminal: unzip, `npm install`, `npm run build` | "I unzip it, install and build. It compiles." |
| 2:40 to 2:55 | Docs page, Accessibility section, or GitHub Actions green check | "The test suite compiles each server and talks to it through a real MCP client. The accessibility audit reports zero violations in English, German and Spanish." |
| 2:55 to 3:00 | Logo and site address | "MCP Builder. Describe it, hear it, download it." |

Tips

- If the build is slow, cut the waiting in the edit rather than talking over it.
- Optional 10 second shot: after the purchase, open `/admin.html` and show the numbers you just created. Say: "These numbers are real events. The support inbox is private on purpose because it holds personal data."
- Do not claim things that are demo. The judges' page and README already say which parts are simulated.
- Optional: show Windows Narrator reading the result page for five seconds, to prove the screen reader path.
