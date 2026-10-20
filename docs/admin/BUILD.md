# Build Guide

## Local development

```bash
make env
make dev-base   # only after base dependency changes or on a new machine
make dev-build
make dev-up
```

The local base is `ml-portal-base-ml:latest`. It is intentionally unrelated to
production release tags.

MCP images install dependencies from the selected server's `requirements.txt`
before copying its source. The dependency layer is reused while that file is
unchanged, and changes to another MCP server do not invalidate the image's
source layer.

## Production release

Production images are built only on a DevOps workstation from a clone of the
production GitLab repository. See [Release Workflow](RELEASE_WORKFLOW.md) for
repository setup and registry prerequisites.

```bash
make update-source
make release-check
make release
```

`make release` discovers all buildable services from
[`docker-compose.build.yml`](../../docker-compose.build.yml); adding a service
with both `build:` and a fully-qualified `image:` needs no Makefile change.

The build compose also publishes `/hipporag:${APP_IMAGE_TAG}` from
`mcp/hipporag/Dockerfile`, using the same immutable `BASE_IMAGE` as API/worker.
HippoRAG dependencies and its pinned upstream revision are installed during the
workstation build; production runs the prebuilt image without downloading models
or packages. The deployment application-service list includes `hipporag`.

The release manifest records two independent versions:

- `APP_IMAGE_TAG` changes for every release.
- `BASE_IMAGE_TAG` uses `base-MAJOR.MINOR` and changes only when the hash of
  the base Dockerfile or base requirements changes.

Application images use immutable, fully-qualified internal Registry names. The
production VM only pulls those images through its internal network; it does not
need internet access and does not pull the base image separately.
