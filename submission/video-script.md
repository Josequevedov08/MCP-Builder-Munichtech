# Three minute video script

Target length: 2:45 to 2:55, never above 3:00. The narration is generated with ElevenLabs (one audio file per scene) and laid over a silent screen recording. The site's own spoken report is left audible in scene 4.

Demo choice: use the Files source for the whole flow, so the generated server can be connected to Claude Desktop with no database.

Before recording

1. Open https://mcpbuilder-api.quevedojose.com/api/health until it answers (wakes the free server).
2. Site in English, browser zoom 100 percent, one clean window, notifications off.
3. Create a folder `C:\demo-docs` with 3 or 4 fake files (`clients.csv`, `notes.txt`, `prices.csv`). No real data.
4. Have an empty folder and a terminal ready. Have Claude Desktop installed and closed.
5. Do one full dry run so the timings are true.

## Narration (paste each block into ElevenLabs as its own clip)

Scene 1, hook (0:00)
Connecting company data to an AI assistant with MCP takes days of careful work. And for a blind developer, build tools are even harder, because progress is shown on a screen. MCP Builder fixes both.

Scene 2, live status (0:15)
The home page checks the live service. The open-weight model on Featherless.ai and the ElevenLabs voice are both online, and the counter shows real servers generated.

Scene 3, builder (0:30)
I choose a files source, name my server, and point it to a folder. Then I write my rules in plain words: read only, small files, no secrets. I write no code. Payment runs in test mode, so nothing is charged.

Scene 4, result (1:00)
The build report is read aloud, in the language I chose.
[pause about 8 seconds: the site speaks]
The same text is on the page for screen readers. Below are the rules the AI derived from my sentence, so I can verify what it understood.

Scene 5, files and download (1:30)
The AI only writes this small policy. The server code comes from verified templates that we compile and test, so it always builds and the security checks are always there. I download the zip, and it also arrives by email with my receipt.

Scene 6, terminal and Claude Desktop (1:55)
I unzip it, install and build. It compiles. Now I add it to Claude Desktop and ask about my files. It answers from my folder, and stays inside the rules.

Scene 7, proof (2:25)
The usage page shows real events from this session. Our test suite compiles each generated server and drives it through a real MCP client, and the accessibility audit reports zero violations in English, German and Spanish.

Scene 8, closing (2:45)
MCP Builder. Describe it, hear it, download it.

## On screen

| Scene | Show |
| --- | --- |
| 1 | Landing page hero |
| 2 | Live service status card, then scroll slowly |
| 3 | Quote builder filled in, "Fill in test card", pay |
| 4 | Result page: audio plays, then the rules list |
| 5 | File preview, click Download server.zip, then the receipt email with the zip |
| 6 | Terminal: unzip, `npm install`, `npm run build`. Then Claude Desktop asking about the folder |
| 7 | `/admin.html` numbers, then the green GitHub Actions check |
| 8 | Logo and site address |

Tips

- Cut the waiting (build, npm install) in the edit rather than talking over it.
- Do not claim things that are demo. Say "test mode" for payment.
- Optional five seconds of Windows Narrator reading the result page.
