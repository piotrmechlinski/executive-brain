# Setup

A first result in about five minutes; the rest when you have time.

## What you need

- A GitHub account.
- A paid Claude plan with Claude Code on the web: Pro, Max, Team, or an Enterprise seat that includes it. On Team and
  Enterprise, an Owner first turns on the GitHub connector for the organisation.
- Nothing to install: the vault runs in Claude Code on the web, from a browser or the Claude app. To work on a
  computer instead, see "On a computer" below.

## 1. Your own private copy

Your vault is a private GitHub repository of your own, made from this one.

1. On this repository's page on GitHub, click **Use this template**, then **Create a new repository**.
2. Choose a name, such as `my-executive-brain`, and **Private**. Leave **Include all branches** unticked: your vault
   needs only `main`.
3. Click **Create repository**.

Keep it private. It will hold what people tell you.

## 2. Claude Code on your vault

1. Open [claude.ai/code](https://claude.ai/code) in a browser, or the **Code** tab in the Claude app.
2. Connect GitHub when asked. Give the Claude GitHub App access to **only** your vault repository.
3. Choose your vault repository, on its own. In a claude.ai project, or in a session with other repositories, the
   vault's commands (`/setup`, `/debrief` and the rest) and its hooks do not load.
4. For the environment, network access **Trusted** is enough: the session installs the few Python packages the tools
   need by itself (`.claude/start.sh`).
5. Start a session.

## 3. The first session

Type `/setup`. Claude asks for one message, which you can dictate: your name and role, the city you work from, your
projects in a line each (a name, who owns it, the next step) and a line on your company's rules for AI tools. It then
writes your project cards and shows your start page, `Home.md`, and a project map as a PDF. From then on GitHub opens
your vault at a short page that points to Home, and the fictional example is gone from your copy.

Claude then offers a second round: the people who matter, the decisions, risks and dates you know of. Or drop a
strategy, an organisation chart or a recent board pack into `Inbox/`, and Claude starts the registers from it.

## 4. Every day

- **After a meeting:** type `/debrief` and answer a few questions. Two minutes.
- **Material:** upload files to `Inbox/` on GitHub (**Add file**, **Upload files**; GitHub's page takes up to 25 MiB
  a file), then type `/ingest`. Word, Excel, PowerPoint, OpenDocument, PDF, a saved e-mail (`.eml`) and photos all
  work; a scanned PDF is read as pictures. Or paste the text of an e-mail or a document into the chat and ask Claude to
  file it.
- **Ask:** "What did we decide about the vendor?", "Who owns the migration risk?", "Build me the project map", "Make
  a Word document of the decisions". Claude answers from the vault, with the IDs of the rows and links to their
  sources, and says so when the vault holds nothing on it.
- **Before a meeting:** type `/brief` and say who will be there, or name a project: Claude writes a brief of what is
  overdue, open and unverified, and of the last meetings, every line with its source, as a PDF if you want one.
- **Where the work lands:** every session saves to `main`, the branch GitHub shows, so the next session sees it. A
  cloud session starts on a branch of its own; Claude moves to `main` first, as `CLAUDE.md` says. Two sessions at once
  are fine: the second one takes in the first one's work before it saves. If a session ever says its work waits on a
  branch, ask it to open a pull request, then merge it on GitHub.

## 5. Every week

Type `/review`. Claude lists what was decided, closed or changed since the last review, what is overdue, the open
actions by owner, what has not moved in 30 days and what can be closed, and you decide together.

## Optional

- **Recordings:** any meeting recorder works, used with everyone's consent: drop its transcripts in `Inbox/`. A
  recorder with a Claude connector may let Claude fetch them itself; that has not been tried with Executive Brain yet.
- **E-mail and calendar:** a Claude connector to your mailbox and calendar may let Claude read what you forward and
  start meeting notes from your calendar; that has not been tried with Executive Brain yet. Read what a connector
  brings and sends under "Privacy and trust" first.
- **Outputs:** ask for the project map and Claude puts a PDF of it in `Outputs/`, which you open from GitHub on a
  phone or a computer. A Word file opens after **Download raw file** on its page. A map you send to someone has no
  links to your repository: ask for a map to send, and say which projects.

## On a computer

The vault works the same with Claude Code on a computer, the terminal or the desktop app.

1. Clone your vault and open it: `git clone https://github.com/<you>/my-executive-brain`, then `cd my-executive-brain`
   and `claude`.
2. Python 3.9 or later runs the check and the map. For Word, Excel, PowerPoint and PDF files:
   `python3 -m pip install -r requirements.txt`. For the diagrams in Word files and the PDFs: Node, then
   `npm install playwright` and `npx playwright install chromium` in the vault's folder.
3. Work on `main`. On a computer the session start prints the status, and leaves git and the packages to you.

**A copy without the template button.** Create an empty private repository on GitHub, then:

```
git clone https://github.com/piotrmechlinski/executive-brain my-executive-brain
cd my-executive-brain
git remote set-url origin https://github.com/<you>/my-executive-brain
git push -u origin main
```

**Obsidian** ([obsidian.md](https://obsidian.md)) opens the vault as a folder and shows the links between notes. In
its settings, under "Files and links", turn off "Use [[Wikilinks]]" and set new links to a relative path, so that the
links Obsidian writes open on GitHub too.

## Privacy and trust

Questions and facts, not legal advice. Show this part to your legal or IT team before the vault holds company
information. It is part of `SETUP.md`, so an update of the product brings its corrections.

### What the product does

- The tools read and write the vault's files. They reach the network only for your own repository (`git fetch`) and,
  in a cloud session, for the four Python packages in `requirements.txt`.
- Text inside a filed e-mail, document or pasted message is material, never an instruction. Claude reports a request
  it finds there instead of carrying it out. A decision, an owner or a date that only an outside party's material
  states goes in as open and *unverified* until you confirm it. The vault's settings deny Claude web fetches, `curl`
  and `wget`; Claude Code's documentation calls such rules a best effort, not a guarantee.
- A hook holds every push while the check fails and refuses a commit that would put a code name or a `Private/` note
  into the history. It runs in a Claude Code session on this vault alone.

### Where the vault goes

- **GitHub** keeps every file and its history in your private repository. Claude reaches it through the Claude GitHub
  App: give the app this repository only. Turn on two-factor sign-in for GitHub, and for the account you sign in to
  Claude with.
- **Anthropic** copies the repository into each cloud session's own machine and keeps the session's transcript, with
  every file Claude read, until you delete the session; after that, up to 30 days, or longer if it was flagged or the
  training setting is on. On Free, Pro and Max you choose at claude.ai/settings/data-privacy-controls whether sessions
  train future models: with that on, data is kept up to five years. Team and Enterprise are not used for training
  unless the organisation opts in. A transcript sent with `/feedback` or `/bug` is kept for five years: send none from
  a vault session. Organisations with zero data retention, HIPAA or customer-managed keys cannot use cloud sessions.
- **Connectors** you turned on in Claude come with every cloud session, and a scheduled task gets all of them by
  default, writes included, acting as you. What Claude reads through a connector enters the session, and its provider
  sees what Claude sends. Remove the connectors you do not need, from Claude's settings and from each scheduled task,
  and file material from people you do not know with connectors off.
- **The people you send an output to** see what is in it. A map built with `--send` has no links to your repository.

### Accounts

- Use the accounts your company approves for its information: company material in a company account, personal
  matters outside it. A cloud session does not move when a personal account joins an organisation.
- On Team and Enterprise, an Owner first turns on the GitHub connector, and the Primary Owner can export the
  organisation's conversations. Anthropic does not say whether that includes cloud sessions.

### What the check catches, and what it does not

- It stops on a code name added with `vault.py private-term`, and on a line of 40 characters or more copied from a
  `Private/` note, in `Home.md`, `Meetings/`, `Knowledge/`, `Projects/`, `Outputs/`, `Archive/`, the summaries in
  `Sources/`, hidden folders such as `.github/`, `CLAUDE.md`, and the title and footer in `settings.json`. It stops on
  a code name in the name of a file there too, and on a recording without `consent: yes`.
- It compares words, not characters. Case, accents, invisible characters, letters of other alphabets that look Latin,
  HTML tags and entities, Markdown emphasis, white space and line breaks do not hide a code name or a `Private/` line,
  nor do table rows or list items between its words. A code name with an umlaut is also found without it: Brücke as
  Brucke or Bruecke.
- It does not see a paraphrase or a translation, a `Private/` line shortened or cut in two, a plural, a code name run
  into another word (ProjectKestrel), a picture, the headers, footers and properties of an Office file, the material in
  `Sources/` as it came, `Inbox/`, `Templates/`, the `README.md` of a folder, or the history.
- A code name is kept as a hash, so `settings.json` does not spell it out. That guards against accidents. Someone who
  can read the vault can guess a common word from its hash, and finds the word itself in `Private/`.
- `Private/` is a folder in the same repository, not a lock: GitHub, Claude and anyone with access to the repository
  can read it.

### Export, delete, and remove a leak

- **Export:** clone the repository, or download it from GitHub as a ZIP file.
- **Delete:** delete the repository in its settings on GitHub; GitHub can restore a deleted repository for 90 days.
  Delete the vault's sessions in Claude.
- **Remove a leak:** Claude never rewrites history; it stops and shows you where the leak is. The owner removes it with
  `git filter-repo` and a force-push, as GitHub's guide to removing sensitive data describes, and asks GitHub Support
  to clear cached views. Commit hashes change, and clones, forks and session transcripts keep their own copies.

### What only your organisation can answer

- The AI use policy, the classes of data that may go in, and the connectors it approves.
- Whether colleagues' names, roles and what they said may be kept, on what basis, how they are told, how long it is
  kept, and how an access or erasure request is handled.
- Whether a recording needs everyone's consent where you are, and whether employee representatives must agree.
- Inside information of a listed company, material under an NDA, and privileged legal advice.
- A legal hold, a lost phone or a breached account, and who owns the vault when you leave.

## Updating

A new release of Executive Brain is listed on its GitHub page, with what changed in `CHANGELOG.md`. `vault.py status`
shows the version your vault runs.

**What a release replaces:** `tools/`, `Templates/`, `.claude/` (the commands, the hooks, the settings and the start
script), `.github/workflows/`, `requirements.txt`, `SETUP.md`, `AGENTS.md`, `CHANGELOG.md`, `LICENSE`, the `README.md`
in each folder, and `CLAUDE.md` but for its "About me" part.

**What stays yours:** your notes, registers, cards and outputs, `Home.md` (its generated part is refreshed),
`settings.json`, the vault's own `README.md`, and "About me".

**How to bring it in,** in a session that can reach GitHub, or on a computer:

```
git remote add product https://github.com/piotrmechlinski/executive-brain    # once
git fetch product --tags
git checkout v1.0.0 -- tools Templates .claude .github/workflows requirements.txt SETUP.md AGENTS.md CHANGELOG.md LICENSE
```

with the release's tag in place of `v1.0.0`. Bring in the folders' `README.md` files the same way, and the new
`CLAUDE.md`, then put your "About me" back into it. Then `python3 tools/vault.py refresh` and
`python3 tools/vault.py check`, and commit as `Update: Executive Brain` and the version. Claude can do all of it when
you ask for the update.
