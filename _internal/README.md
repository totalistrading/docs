# Internal docs (not published)

These pages are **not** part of the public Totalis documentation site. They are
excluded from the Mintlify build by the `_internal/` entry in `.mintignore` at
the repo root.

## Why the .mintignore entry is load-bearing

Mintlify builds every `.mdx` file it finds. Leaving a page out of `docs.json`
navigation only makes it a *hidden page*: still built, still live at its URL,
just not in the sidebar. That is what happened here. This whole directory was
publicly readable at `docs.totalis.trade/_internal/...` for an unknown period,
including the BYOW / `X-Subaccount` partner surface and the admin reference.

Renaming the directory does not help either; the build follows the files, so a
rename just moves the exposure to a new URL.

**Do not remove the `_internal/` line from `.mintignore`, and do not add these
pages to `docs.json`.**

If any of this content needs to be shared outside the team, put it behind real
authentication or in a private repo. An unlinked URL is not access control.
