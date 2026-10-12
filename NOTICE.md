# Third-party code

keyhub is GPL-3.0-or-later because it includes and links GPL-3.0 code.

| Component | Where | License | Upstream |
|---|---|---|---|
| Toshy runtime (keymap config, `toshy_common`, KWin script and D-Bus service) | `src/keyhub/vendor/toshy/` (pinned in `UPSTREAM`, unmodified) | GPL-3.0 | https://github.com/RedBearAK/toshy |
| xwaykeyz keymapper | Python dependency (pinned commit) | GPL-3.0-or-later | https://github.com/RedBearAK/xwaykeyz |
| Handy | Not included. keyhub controls the installed app over D-Bus | MIT | https://github.com/cjpais/Handy |

To update the vendored Toshy files: `scripts/update-vendor.sh <commit>`.
