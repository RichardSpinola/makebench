# Bundled Blockly page

The Logic area's web page lives in `src/makebench/web` so that it ships inside
the Python package. `index.html` (English), `index.pt_BR.html`, `logic.js` and
`style.css` exchange only data over Qt WebChannel; no bridge function runs
Python or system commands.

Blockly 13.4.0 comes from the official `blockly` npm package, with its SHA-512
integrity checked. `vendor/blockly/vendor-lock.json` records the URL, integrity,
Apache-2.0 license and the copied files: the core and blocks bundles, the `en`
and `pt-br` messages, and images and cursors. Sounds are disabled and not
distributed. The original `LICENSE` and `package.json` are kept. There is no
CDN, no download at run time and no Node.js needed to open the editor.

Updating Blockly requires reviewing the serialization API, the license and the
tests in `checks/blockly_smoke.py`. Test block comments and the explicitly
registered `WorkspaceCommentSerializer` for free comments in particular. Keep
the neutral logic model, and migrate saved versions before changing the protocol.
