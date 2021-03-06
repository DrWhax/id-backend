# The Investigative Dashboard Project API 🕵️

[![Build Status](https://travis-ci.org/occrp/id-backend.svg?branch=master)](https://travis-ci.org/occrp/id-backend)
 [![Translation status](https://hosted.weblate.org/widgets/occrp/-/investigative-dashboard/svg-badge.svg)](https://hosted.weblate.org/engage/occrp/?utm_source=widget)

[OCCRP](https://tech.occrp.org/projects/) research desk application API.

# Prerequisites

- [Docker](https://docs.docker.com/docker-for-mac/install/) (to run just the API)
- [id-frontend](https://github.com/occrp/id-frontend) (to run the whole application)
- [Jekyll Website](https://github.com/occrp/investigativedashboard.org/)
(the homepage of investigativedashboard.org)

# Setup

Please refer to the `id.env.tmpl` for the full list of settings.

Create a superuser to login to the admin:
```bash
docker-compose run --rm api ./manage.py createsuperuser
```

Start the dev server for local development or production:
```bash
docker-compose up
```

Please see the `docker-compose.prod.yml` for production ready deployments.

# Running the tests

To run the tests, use the `docker-compose.dev.yml` configuration and run:
```bash
docker-compose run --rm api ./manage.py test
```

# Preparing a release

To build the production-ready images run:

```bash
docker build --build-arg=ID_VERSION=$(git describe --always) -t occrp/id-backend ./
```

You're now ready to continuously ship! ✨ 💅 🛳
