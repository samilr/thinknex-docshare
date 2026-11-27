# Postgres 17 (alpine) + pgvector para la búsqueda semántica. En Cloud SQL la extensión ya existe.
FROM postgres:17-alpine
ARG PGVECTOR_VERSION=0.8.1
RUN apk add --no-cache --virtual .build-deps git build-base \
    && git clone --depth 1 --branch v${PGVECTOR_VERSION} https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector OPTFLAGS="" with_llvm=no \
    && make -C /tmp/pgvector install with_llvm=no \
    && rm -rf /tmp/pgvector \
    && apk del .build-deps
