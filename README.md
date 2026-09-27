# Totalis Docs

Documentation for the Totalis Parlay RFQ API, built with [Mintlify](https://mintlify.com).

## Development

Install the [Mintlify CLI](https://www.npmjs.com/package/mint) to preview your documentation changes locally. To install, use the following command:

```
npm i -g mint
```

Run the following command at the root of your documentation, where your `docs.json` is located:

```
mint dev
```

View your local preview at `http://localhost:3000`.

## Hyperliquid API reference

The Hyperliquid tab is generated. Regenerate both files from a hip4-backend checkout on current `main`:

```
python3 ../hip4-backend/tools/public_openapi.py --output hyperliquid/openapi.json
python3 scripts/hyperliquid_errors.py --registry ../hip4-backend/protocol/jsonschema/error.schema.json
```

`scripts/hyperliquid_errors.py --check` fails when `hyperliquid/errors.mdx` no longer matches the registry and the spec.

## Publishing changes

Install our GitHub app from your [dashboard](https://dashboard.mintlify.com/settings/organization/github-app) to propagate changes from your repo to your deployment. Changes are deployed to production automatically after pushing to the default branch.

## Need help?

### Troubleshooting

- If your dev environment isn't running: Run `mint update` to ensure you have the most recent version of the CLI.
- If a page loads as a 404: Make sure you are running in a folder with a valid `docs.json`.

### Resources
- [Mintlify documentation](https://mintlify.com/docs)
