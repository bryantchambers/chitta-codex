# chitta-codex-bootstrap

Thin bootstrap layer for installing CHITTA + Codex on a new machine without mutating the production install first.

This repo does not contain the application code. It only:

1. checks out pinned revisions of the existing repos,
2. runs the existing installers,
3. adds a Codex-only `zellij-mcp` config block,
4. backs up Codex config before mutation,
5. verifies the result with Codex CLI smoke checks,
6. and can restore the prior Codex config.

## Pinned inputs

- `cc-soul` @ `9911bd436c019783beffc0e37bf252214dc8dbd1`
- `chitta-bridge` @ `17fa57f06cc6e0f18bb8ee29b071d8e07398c66a`
- `zellij-mcp` @ `c62c51dc338a4392e076ac96a98f6e8bdcee6fca`

## Entry points

```bash
./bootstrap.sh install
./bootstrap.sh install --dry-run
./bootstrap.sh verify
./bootstrap.sh rollback
```

## Safety model

- The bootstrap repo keeps its own backups under `backups/`.
- `install` backs up Codex config before changing anything.
- `rollback` restores the saved config or removes the managed `zellij-mcp` block if no backup exists.
- No code here touches the current production install unless you explicitly run it.

## Notes

- `zellij-mcp` is registered in Codex with an explicit Python interpreter and a startup timeout.
- `cc-soul` and `chitta-bridge` are still installed through their existing repo installers.
- The bootstrap wrapper requires a usable Python 3.11+, or Python 3.10 with `tomli` available.
