# Installing, self-hosting and publishing Entity Controller

## Read this first

* **HACS can only install from public GitHub repositories.** The HACS
  documentation states that only public repositories hosted on GitHub are
  compatible. A repository on a self-hosted git server (Gitea, Forgejo,
  GitLab, a NAS, …) — and a *private* GitHub repository — cannot be added to
  HACS as a custom repository. For self-hosting, use the install script
  described below; switch to HACS once (and if) you publish on GitHub.
* This fork uses the same folder and domain as the original
  (`custom_components/entity_controller`). **Remove the original Entity
  Controller from HACS first** (HACS → Entity Controller → ⋮ → Remove) or
  delete its folder. Your YAML configuration and entity ids are kept and
  imported automatically.
* Requires Home Assistant **2025.1 or newer** (tested with 2025.1.4 and
  2026.9.4). The integration icon is shown from Home Assistant 2026.3.

After installing with any method, restart Home Assistant. Then:

* **No YAML controllers yet:** Settings → Devices & services → *Add
  integration* → search **Entity Controller**. This creates your first
  controller; further controllers are added with **Add controller** on the
  integration page.
* **Existing `entity_controller:` YAML:** the controllers are imported
  automatically and appear on the integration page (Settings → Devices &
  services → Integrations → Entity Controller). See *Migrating* in the
  [README](../README.md).

Everything else is managed on that integration page (see *Managing
controllers* in the README).

---

## Option 1 — Copy the files (any installation type)

Copy the folder `custom_components/entity_controller` from this repository
into the `custom_components` folder of your Home Assistant configuration
directory (create it if needed), so that you end up with
`/config/custom_components/entity_controller/manifest.json`. Then restart
Home Assistant.

* **Home Assistant OS / Supervised:** use the *Samba share*, *Terminal & SSH*
  or *Studio Code Server* add-on to reach `/config`.
* **Container:** copy into the directory mounted as `/config`.
* **Core (venv):** copy into your configuration directory (usually
  `~/.homeassistant`).

## Option 2 — Self-hosted git server + install script

This gives you a versioned, repeatable install/update from your own server.

### 2a. Put the repository on your server

Create an empty repository on your server (Gitea/Forgejo/GitLab web UI), then
from this folder:

```bash
git remote add origin https://git.example.lan/me/entity-controller-ui.git
git push -u origin master
git tag v10.0.0
git push origin v10.0.0
```

(`upstream` already points to the original project, in case you want to look
at future upstream changes with `git fetch upstream`.)

Your server offers every tag/branch as an archive:

| Server | Archive URL |
|---|---|
| Gitea / Forgejo | `https://git.example.lan/me/entity-controller-ui/archive/v10.0.0.tar.gz` |
| GitLab | `https://gitlab.example.lan/me/entity-controller-ui/-/archive/v10.0.0/entity-controller-ui-v10.0.0.tar.gz` |

Use a branch name (e.g. `master`) instead of the tag to always get the latest
commit. Any web server hosting a `.tar.gz` or `.zip` of the repository works
too.

### 2b. Install / update on Home Assistant

On Home Assistant OS open the *Terminal & SSH* or *Advanced SSH & Web
Terminal* add-on (on Container/Core use a shell on the host and pass your
configuration directory as second argument). Copy `scripts/install.sh` to
`/config/install.sh` (e.g. with the Samba share), then:

```bash
sh /config/install.sh https://git.example.lan/me/entity-controller-ui/archive/v10.0.0.tar.gz
ha core restart
```

For a private repository pass a token:

```bash
EC_HEADER="Authorization: token YOUR_GITEA_TOKEN" sh /config/install.sh https://git.example.lan/me/entity-controller-ui/archive/v10.0.0.tar.gz
```

(GitLab: `EC_HEADER="PRIVATE-TOKEN: YOUR_TOKEN"`.) The script also accepts a
local archive or a local directory such as a git clone:

```bash
git clone https://git.example.lan/me/entity-controller-ui.git /config/ec-src
sh /config/ec-src/scripts/install.sh /config/ec-src
# later: git -C /config/ec-src pull && sh /config/ec-src/scripts/install.sh /config/ec-src
```

The previous version is moved to `/config/entity_controller.backup`; the
script prints the command to roll back.

### 2c. Optional: update from the Home Assistant UI

Add a shell command to `configuration.yaml` and restart once:

```yaml
shell_command:
  update_entity_controller: >-
    sh /config/install.sh https://git.example.lan/me/entity-controller-ui/archive/master.tar.gz
```

Then run the action `shell_command.update_entity_controller` (e.g. from a
script or a dashboard button) followed by `homeassistant.restart`. Shell
commands run inside the Home Assistant container with a 60 second timeout;
if the command fails there, run it from the SSH add-on instead.

---

## Option 3 — Publish on GitHub and install with HACS

The GitHub repository is **JohnDepon/entity-controller-ui**, a fork of
danobot/entity-controller. The repository already has the layout HACS
expects (`hacs.json`, a single integration in `custom_components/`, a
`manifest.json` with all required keys pointing to this repository, and a
brand icon in `custom_components/entity_controller/brand/`).

1. **Create the fork** (once): open https://github.com/danobot/entity-controller,
   click **Fork**, owner *JohnDepon*, repository name `entity-controller-ui`,
   keep *Copy the master branch only* ticked → *Create fork*. A fork of a
   public repository is always public.
2. **Push** (the `origin` remote is already set up in this repository):

   ```bash
   git push -u origin master
   ```

   If `origin` is missing (e.g. in a fresh clone of the original), add it
   first with `git remote add origin https://github.com/JohnDepon/entity-controller-ui.git`.
3. In the fork's **Settings**: enable *Issues* (General → Features; forks
   have them off, and the integration's issue link points there). On the
   repository page set a **description** (shown by HACS) and **topics** such
   as `home-assistant`, `hacs`, `homeassistant-integration`.
4. Open the **Actions** tab and enable workflows (paused in forks), then
   wait for the **Validate** workflow to pass: it runs the HACS validation,
   Home Assistant's `hassfest` and the tests.
5. **Create a release** (recommended): Releases → *Draft a new release* →
   tag `v10.0.0` → paste the notes from `CHANGELOG.md` → *Publish*. HACS
   offers the five latest releases; without releases it installs the default
   branch.
6. **Install in Home Assistant:** HACS → ⋮ (top right) → *Custom
   repositories* → Repository `https://github.com/JohnDepon/entity-controller-ui`,
   Type *Integration* → *Add*. Open the new *Entity Controller* entry (check
   that it shows JohnDepon/entity-controller-ui), *Download*, then restart
   Home Assistant.

Submitting the fork to the HACS *default* store is not recommended: the
original Entity Controller is already listed there with the same domain.

## Releasing a new version (all options)

1. Change the code, run the tests (`pip install -r requirements_test.txt`,
   then `pytest`).
2. Increase `version` in `custom_components/entity_controller/manifest.json`
   (the only place holding the version) and add a section to `CHANGELOG.md`.
3. Commit, tag `vX.Y.Z` and push the tag.
4. Self-hosted: run the install script with the new tag's archive URL.
   GitHub/HACS: create a GitHub release for the tag; HACS then offers the
   update.

## License obligations when sharing it

Entity Controller is licensed under the GNU GPL v3, and so is this fork. When
you publish or give it to others: keep `COPYING` and the license notices in
the files, keep the notice that this is a modified version (README and
`CHANGELOG.md` already state it, with the date), and distribute it under the
GPLv3. Publishing the repository itself provides the source code.
