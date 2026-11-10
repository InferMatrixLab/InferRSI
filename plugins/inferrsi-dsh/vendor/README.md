# SSH transport bundle

`ssh2.cjs` is generated from `ssh2` 1.17.0 with esbuild 0.25.12. It includes
the pure JavaScript transport and dependencies. Optional `cpu-features` and
native `*.node` acceleration stay external and use the library's standard
fallback when absent. No lifecycle scripts execute when installing InferRSI.

Source and license text are retained in `THIRD_PARTY_NOTICES.md`.

To regenerate in a disposable build directory, install the exact source and
build-tool packages with scripts disabled, then bundle the package entry.
Use the platform-specific esbuild binary dependency for the build machine.

```text
npm install --prefix <BUILD_DIRECTORY> --ignore-scripts ssh2@1.17.0 esbuild@0.25.12
cd <BUILD_DIRECTORY>
node node_modules/esbuild/bin/esbuild node_modules/ssh2/lib/index.js --bundle --platform=node --format=cjs --target=node22 --external:cpu-features --external:*.node --legal-comments=inline --outfile=<SOURCE_ROOT>/plugins/inferrsi-dsh/vendor/ssh2.cjs
```

Reconcile the included `ssh2`, `asn1`, `safer-buffer`, `bcrypt-pbkdf` and
`tweetnacl` license files and versions when refreshing the bundle. Run
`node tests/check_dsh_remote.cjs` and the native DSH installation check before
shipping a regenerated bundle.

The checked-in output removes trailing spaces from one empty line in an
upstream RFC comment to satisfy the repository whitespace check.

## YAML parser bundle

`yaml.cjs` is generated from `yaml` 2.9.1 with esbuild 0.25.12. It exposes the
document parser and map/scalar checks through the packaged browser client.
The importer checks the document structure before using any values.

In a disposable build directory, install the exact dependencies, then create
`parser.mjs` with this single line:

```js
export { isMap, isScalar, parseDocument } from 'yaml';
```

```text
npm install --ignore-scripts yaml@2.9.1 esbuild@0.25.12
node node_modules/esbuild/bin/esbuild parser.mjs --bundle --platform=browser --format=cjs --target=es2022 --legal-comments=inline --outfile=<SOURCE_ROOT>/plugins/inferrsi-dsh/vendor/yaml.cjs
```
